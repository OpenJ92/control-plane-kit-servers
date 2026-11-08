"""Real isolated workspace and encrypted-provider key commissioning for #163.

This stage never prepares, approves or executes a deployment. It uses the
production Operations factory and actual authenticated Secrets API. Provider
HTTP uses the existing TestClient bridge; the maintained command-service driver
supplies trusted test principals to the grandparent services.
"""
import asyncio
import base64
from dataclasses import replace
import json
import importlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
import control_plane_kit_core as core
from control_plane_kit_core.identity import PrincipalKind
from control_plane_kit_core.operations import ControlPlaneServiceRole as Role
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.secrets import SecretReference, SecretUseIntent, health_signing_intent_for, http_verification_sample_signing_intent_for
from control_plane_kit_interpreters.secret_provider import canonical_provider_secret_id
from control_plane_kit_interpreters.docker import DockerUnixSocketClientConfig
from control_plane_kit_operations.managed_runtime_assignments import ManagedRuntimeCapability, ManagedRuntimeCapabilityPolicy
from control_plane_kit_operations.workflows import IdempotencyKey
from control_plane_kit_operations.workspace_permissions import (
    WorkspaceAdministrationContext, WorkspaceAdministrationPolicy, WorkspacePermissionCommandService,
)
from control_plane_kit_operations.http_sample_execution import HttpSampleExecutionSupport
from control_plane_kit_servers_cpk_server import server
from control_plane_kit_servers_cpk_server.operations_application import (
    OperationsApplicationFactory, OperationsIdFactories, WorkspaceAuthorityConfiguration,
)
from control_plane_kit_servers_cpk_server.managed_health_configuration import ManagedHealthProcessConfiguration
from control_plane_kit_servers_cpk_server.managed_health_placement import DockerRuntimeCapabilityBinding
from control_plane_kit_servers_cpk_server.http_sample_composition import gateway_http_sample_binding
from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import gateway_http_sample_trust_from_artifact
from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import decode_gateway_health_transit_configuration
from control_plane_kit_core.http_verification_sample_installation import HttpVerificationSampleReceiverConfigurationCodec
from protected_input_provider import ProtectedProvider, PROVIDER, TOKEN
from receiver_acceptance_operations import IsolatedOperationsSchema, PublicOperationsDriver, utc_now, witness_principal
from test_secret_provider_bootstrap import _provider_environment
from http_sample_installation_assembly import assemble


def signing_inputs(fixture, original, graph, custody):
    """Read actual installed public trust and matching fixture-private inputs."""
    gateway = graph.node(original.management.runtime_management.gateway_node_id)
    artifacts = {entry.artifact_id: entry for entry in gateway.configuration_artifacts}
    transit = gateway_http_sample_trust_from_artifact(artifacts["gateway-http-sample-transit"])
    health = decode_gateway_health_transit_configuration(artifacts["gateway-health-transit"].content.encode())
    samples = []
    for node_id, artifact_id in ((original.cpk_node_id, "cpk-http-samples"),
                                 (original.secrets_node_id, "secrets-http-samples")):
        artifact, = (entry for entry in graph.node(node_id).configuration_artifacts if entry.artifact_id == artifact_id)
        samples.append(HttpVerificationSampleReceiverConfigurationCodec().decode_canonical_bytes(artifact.content.encode()))
    assert samples[0].verifier == samples[1].verifier
    own = fixture.receiver(graph.node(original.cpk_node_id))
    rows = []
    def row(name, purpose, issuer, key, private, intent):
        assert type(key) is core.DelegationPublicKey
        loaded = serialization.load_pem_private_key(private, password=None)
        public = loaded.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
        assert public == key.public_key_pem, "fixture material does not match installed trust"
        rows.append(dict(name=name, purpose=purpose, issuer=issuer, key=key, private=private,
            intent=intent, reference=SecretReference(f"secret://{PROVIDER}/keys/{name}")))
    purpose = core.DelegationKeyPurpose.GATEWAY_HTTP_VERIFICATION_SAMPLE_TRANSIT
    row("sample-transit", purpose, transit.issuer, transit.public_keys[0],
        fixture.sample_signing_material.private["transit"], http_verification_sample_signing_intent_for(purpose))
    purpose = core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE
    row("sample-workload", purpose, samples[0].verifier.issuer, samples[0].verifier.public_keys[0],
        fixture.sample_signing_material.private["workload"], http_verification_sample_signing_intent_for(purpose))
    purpose = core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT
    row("health-transit", purpose, health.issuer, health.public_keys[0],
        fixture.signing_material.private["transit"], health_signing_intent_for(purpose))
    for purpose, filename in ((core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, "health-read.pem"),
                              (core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ, "surface-read.pem")):
        verifier, = (entry for entry in own.verifiers if entry.purpose is purpose)
        intent = (health_signing_intent_for(purpose) if filename == "health-read.pem"
            else SecretUseIntent.GATEWAY_PROBE_SIGNING_KEY)
        row("health-workload" if filename == "health-read.pem" else "surface-workload",
            purpose, verifier.issuer, verifier.public_keys[0], (custody / filename).read_bytes(), intent)
        for node_id in (original.secrets_node_id, original.postgres_node_id):
            installed, = (entry for entry in fixture.receiver(graph.node(node_id)).verifiers if entry.purpose is purpose)
            assert installed == verifier, "installed child verifier does not match commissioned role"
    assert len({entry["key"].fingerprint_sha256 for entry in rows}) == len(rows), \
        "distinct signing roles must not share private signing material"
    return rows


async def commission(schema, root, fixture, original, graph, gateway_document, rows, provider):
    workspace = original.workspace_id
    scopes = tuple(PolicyScope)
    principals = {name: witness_principal(workspace, subject_id="source-" + name,
        kind=PrincipalKind.WORKER if name == "worker" else PrincipalKind.OPERATOR, scopes=scopes)
        for name in ("administrator", "operator", "worker", "approver")}
    administrator = principals["administrator"]
    policy = WorkspaceAdministrationPolicy("source-163-registration", (administrator.identity,),
        tuple(principal.identity for principal in principals.values()))
    capability = ManagedRuntimeCapability("source-163-docker")
    authority = WorkspaceAuthorityConfiguration(policy, ManagedRuntimeCapabilityPolicy(policy.installation_id, (capability,)))
    WorkspacePermissionCommandService(schema.unit_of_work, administration_policy=policy,
        clock=utc_now, id_factory=lambda: uuid4().hex).initialize(
            WorkspaceAdministrationContext(administrator.identity, policy.installation_id),
            idempotency_key=IdempotencyKey("initialize-source-registration"))
    environment = {**_provider_environment(provider.token_file), "CPK_INGRESS_INTERPRETERS": "cloudflare",
        "CPK_MATERIAL_PROVIDER_ROUTES_JSON": json.dumps({PROVIDER: "https://input-provider.invalid"})}
    config = server.CpkServerBootstrapConfiguration.from_environment(environment)
    unix = DockerUnixSocketClientConfig("/var/run/source-fixture-not-opened.sock", 5.0)
    process = ManagedHealthProcessConfiguration(unix, None, (gateway_document,),
        original.management.connector_product, (DockerRuntimeCapabilityBinding(capability, unix),))
    config = replace(config, workspace_authority=authority, managed_health_process=process,
        http_sample_support=HttpSampleExecutionSupport(gateway_http_sample_binding(gateway_document), "control"))
    composition = server._secret_provider_composition(config, transport=provider.transport)
    ports = server._operations_effect_ports(config, composition, unit_of_work_factory=schema.unit_of_work)
    factory = OperationsApplicationFactory(schema.unit_of_work, ports,
        OperationsIdFactories(*(lambda: uuid4().hex for _ in range(5))), workspace_authority=authority, clock=utc_now)
    driver = PublicOperationsDriver(factory, workspace_id=workspace)
    driver.operator, driver.worker = principals["operator"], principals["worker"]
    calls = []
    async def call(route, payload, *, role=Role.PLANNING, principal=None, create=False):
        result = await driver.invoke(route, role, path={} if create else {"workspace_id": workspace},
            payload=payload, principal=principal)
        calls.append(route)
        assert "PRIVATE KEY" not in json.dumps(result) and TOKEN not in json.dumps(result)
        return result
    await call("command.workspace-administration.create", {"workspace_id": workspace,
        "name": "Source child fixture", "idempotency_key": "create-source-workspace"},
        role=Role.AUTHORIZATION, principal=administrator, create=True)
    for name in ("operator", "worker", "approver"):
        await call("command.workspace-permission.grant", {"target": principals[name].identity.descriptor(),
            "scopes": [scope.value for scope in scopes], "expected_revision": 0,
            "idempotency_key": "grant-source-" + name}, role=Role.AUTHORIZATION, principal=administrator)
    admitted_at = utc_now()
    registered = await call("command.secret-provider.register", {"provider_id": PROVIDER,
        "display_name": "Owned encrypted source fixture", "provider_kind": "control-plane-kit-secrets",
        "endpoint_reference": PROVIDER, "credential_reference": "secret://bootstrap/provider-token",
        "allowed_reference_prefixes": [f"secret://{PROVIDER}/keys"],
        "allowed_intents": sorted({row["intent"].value for row in rows}), "admitted_at": admitted_at,
        "metadata": {"source_fixture": "163"}, "idempotency_key": "register-source-provider"})
    receipts = []
    for row in rows:
        secret_id = canonical_provider_secret_id(row["reference"])
        url = f"/v1/workspaces/{workspace}/secrets/{secret_id}"
        written = provider.client.post(url, headers={"Authorization": "Bearer " + TOKEN}, json={
            "value_base64": base64.b64encode(row["private"]).decode("ascii"), "intent": row["intent"].value,
            "caller_subject": "source-operator", "correlation_id": "write-" + row["name"]})
        assert written.status_code == 200, "provider refused fixture custody"
        metadata = written.json()["metadata"]
        reference = await call("command.secret-reference.register", {"reference": row["reference"].reference_id,
            "provider_registration_id": registered["registration_id"], "allowed_intents": [row["intent"].value],
            "admitted_at": admitted_at, "metadata": {"source_fixture": "163"},
            "idempotency_key": "reference-" + row["name"]})
        key = row["key"]
        record = await call("command.delegation-key.register", {"purpose": row["purpose"].value,
            "issuer": row["issuer"], "key_id": key.key_id, "algorithm": key.algorithm.value,
            "public_key_pem": key.public_key_pem, "private_key_reference": row["reference"].reference_id,
            "admitted_at": admitted_at, "idempotency_key": "key-" + row["name"]})
        assert record["status"] == "verify-only" and record["fingerprint_sha256"] == key.fingerprint_sha256
        active = await call("command.delegation-key.activate", {"purpose": row["purpose"].value,
            "issuer": row["issuer"], "key_id": key.key_id, "activated_at": admitted_at,
            "idempotency_key": "activate-" + row["name"]})
        assert active["status"] == "active" and active["registration_id"] == record["registration_id"]
        resolved = provider.client.post(url + "/resolve", headers={"Authorization": "Bearer " + TOKEN}, json={
            "intent": row["intent"].value, "version_id": metadata["version_id"],
            "caller_subject": "source-operator", "correlation_id": "confirm-" + row["name"]})
        assert resolved.status_code == 200, "provider refused exact-version fixture confirmation"
        loaded = serialization.load_pem_private_key(base64.b64decode(resolved.json()["value_base64"]), password=None)
        assert loaded.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii") == key.public_key_pem
        receipts.append(dict(purpose=row["purpose"].value, issuer=row["issuer"], key_id=key.key_id,
            fingerprint_sha256=key.fingerprint_sha256, registration_id=record["registration_id"],
            provider_registration_id=registered["registration_id"], reference_registration_id=reference["registration_id"],
            version_id=metadata["version_id"], status=active["status"]))
    driver.reconstruct()
    readback = await call("read.delegation-keys", {"limit": 100}, role=Role.READS)
    assert len(readback["items"]) == len(receipts)
    for row in receipts:
        item, = (entry for entry in readback["items"] if entry["registration_id"] == row["registration_id"])
        assert all(item[key] == row[key] for key in ("purpose", "issuer", "key_id", "fingerprint_sha256", "status"))
    state = await driver.workspace()
    assert state["desired_graph_id"] is None
    assert not any(route.startswith("command.deployment.") for route in calls)
    return dict(evidence="real-isolated-key-registration-only", workspace_id=workspace,
        keys=receipts, registered_keys=len(receipts), public_calls=len(calls),
        deployment_commands=0, completed_run=False, provider_transport="ASGI to real encrypted Secrets API",
        factory="production dynamic workspace authority and actual registered adapters")


def main():
    imports = {}
    for module, root in (("control_plane_kit_core", "/reviewed-http-sample/core/src"),
                         ("control_plane_kit_operations", "/reviewed-http-sample/operations/src"),
                         ("control_plane_kit_interpreters", "/reviewed-http-sample/interpreters/src"),
                         ("control_plane_kit_secrets.provider_policy", "/reviewed-http-sample/secrets/src")):
        path = Path(importlib.import_module(module).__file__).resolve()
        assert path.is_relative_to(root), "registration source cohort differs"
        imports[module] = str(path)
    database = os.environ["CPK_SOURCE_FIXTURE_DATABASE_URL"]
    previous = Path.cwd()
    with TemporaryDirectory(prefix="cpk163-commission-") as directory:
        root = Path(directory)
        try:
            os.chdir(root)
            custody = root / "commissioning"
            custody.mkdir(mode=0o700)
            fixture, original, _, graph, gateway_document, _ = assemble(commissioning_directory=custody)
            rows = signing_inputs(fixture, original, graph, custody)
            intents = tuple(sorted({row["intent"].value for row in rows}))
            with ProtectedProvider(workspace_id=original.workspace_id, write_intents=intents, resolve_intents=intents) as provider, \
                    IsolatedOperationsSchema(database, "cpk_1912_" + uuid4().hex) as schema, \
                    patch("docker.DockerClient", side_effect=AssertionError("registration entered Docker effects")), \
                    patch("docker.from_env", side_effect=AssertionError("registration entered ambient Docker")):
                result = asyncio.run(commission(schema, root, fixture, original, graph, gateway_document, rows, provider))
                assert not provider.transport.calls, "this stage unexpectedly resolved through an Operations execution"
        finally:
            os.chdir(previous)
    assert not root.exists(), "owned commissioning custody remains"
    result["cleanup"] = "provider and commissioning directories removed; isolated schema dropped"
    result["source_imports"] = imports
    result["secrets_source_revision"] = os.environ["CPK_SOURCE_SECRETS_REVISION"]
    result["operations_database"] = "owned PostgreSQL test service; not the child SQL target"
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
