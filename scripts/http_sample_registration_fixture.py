"""Real isolated key and optionally selected-graph commissioning for #163.

This stage never prepares, approves or executes a deployment. It uses the
production Operations factory and actual authenticated Secrets API. Provider
HTTP uses the existing TestClient bridge; the maintained command-service driver
supplies trusted test principals to the grandparent services.
An explicit immutable image also commissions complete installation versions and
authors desired from this same graph and custody, never a second assembly.
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
from control_plane_kit_core.secret_selections import SecretVersionSelection, secret_selections_from_descriptor
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph
from control_plane_kit_core.topology.secret_selection import carry_forward_secret_selections
from control_plane_kit_servers_cpk_server.installation import installation_secret_version_choices
from control_plane_kit_secrets.crypto import encode_master_key_for_file
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
from http_sample_installation_assembly import assemble, image_options


def signing_inputs(fixture, original, graph, custody, *, provider_id=PROVIDER):
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
            intent=intent, reference=SecretReference(f"secret://{provider_id}/keys/{name}")))
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


async def commission(schema, root, fixture, original, graph, gateway_document, rows, provider,
                     *, selected_image=None):
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
        "CPK_MATERIAL_PROVIDER_ROUTES_JSON": json.dumps({provider.provider_id: "https://input-provider.invalid"})}
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
    intents = {row["intent"].value for row in rows}
    if selected_image is not None:
        intents.update(value.intent.value for node in graph.nodes.values() for value in node.secret_selections)
    registered = await call("command.secret-provider.register", {"provider_id": provider.provider_id,
        "display_name": "Owned encrypted source fixture", "provider_kind": "control-plane-kit-secrets",
        "endpoint_reference": provider.provider_id, "credential_reference": "secret://bootstrap/provider-token",
        "allowed_reference_prefixes": [f"secret://{provider.provider_id}/keys"] + (
            [f"secret://{provider.provider_id}/root-a"] if selected_image is not None else []),
        "allowed_intents": sorted(intents), "admitted_at": admitted_at,
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
    result = dict(evidence="real-isolated-key-registration-only", workspace_id=workspace,
        keys=receipts, registered_keys=len(receipts), public_calls=len(calls),
        deployment_commands=0, completed_run=False, provider_transport="ASGI to real encrypted Secrets API",
        factory="production dynamic workspace authority and actual registered adapters")
    if selected_image is not None:
        result.update(await author_selected_installation(call, driver, provider, schema, fixture, original,
            graph, selected_image, registered, admitted_at))
    result["public_calls"] = len(calls)
    return result


async def author_selected_installation(call, driver, provider, schema, fixture, original, graph,
                                       image, registered, admitted_at):
    """Write actual inputs, then author complete choices via the normal owner."""
    child_token = uuid4().hex
    material = {
        original.control_credential: uuid4().hex.encode("ascii"),
        original.postgres_password: uuid4().hex.encode("ascii"),
        original.custody_root_key: encode_master_key_for_file(os.urandom(32)).encode("ascii"),
        original.provider_client_credential: child_token.encode("ascii"),
        original.provider_credentials_document: json.dumps([{
            "subject": "isolated-child-control-plane", "token": child_token,
            "grants": [{"action": "secret.resolve", "workspace_id": original.workspace_id,
                "intents": ["application.control-token", "postgres.password"]}],
        }]).encode("utf-8"),
    }
    uses = sorted({(entry.reference, entry.intent) for node in graph.nodes.values()
        for entry in node.secret_selections}, key=lambda pair: (pair[0].reference_id, pair[1].value))
    assert {reference for reference, _ in uses} == set(material)
    selections = []
    for index, (reference, intent) in enumerate(uses):
        assert reference.provider_id.value == provider.provider_id
        written = provider.client.post(
            f"/v1/workspaces/{original.workspace_id}/secrets/{canonical_provider_secret_id(reference)}",
            headers={"Authorization": "Bearer " + TOKEN}, json={
                "value_base64": base64.b64encode(material[reference]).decode("ascii"),
                "intent": intent.value, "caller_subject": "source-operator",
                "correlation_id": f"installation-write-{index}"})
        assert written.status_code == 200, "provider refused installation input custody"
        version = written.json()["metadata"]["version_id"]
        selections.append(SecretVersionSelection(reference, intent, version))
        await call("command.secret-reference.register", {"reference": reference.reference_id,
            "provider_registration_id": registered["registration_id"], "allowed_intents": [intent.value],
            "admitted_at": admitted_at, "metadata": {"source_fixture": "163"},
            "idempotency_key": f"installation-reference-{index}"})
    choices = installation_secret_version_choices(original, tuple(selections))
    # Preserve the once-assembled graph and its verifier material. This local
    # expected value never substitutes for the public owner's metadata checks.
    selected = carry_forward_secret_selections(DeploymentGraph(graph.name), graph,
        {node: secret_selections_from_descriptor(values) for node, values in choices.items()})
    for index, document in enumerate(fixture.product_documents):
        imported = await call("command.product.import", {
            "descriptor_document": json.loads(document.content), "imported_at": admitted_at,
            "idempotency_key": f"installation-product-{index}"})
        assert imported["status"] == "active"
    before = await driver.workspace()
    session = await call("command.operation-session.start", {"title": "Select isolated child installation",
        "metadata": {}, "idempotency_key": "installation-authoring-session"}, role=Role.LIFECYCLE)
    names = ("current_graph_id", "current_realized_projection_id", "desired_graph_id",
        "desired_realized_projection_id", "desired_graph_revision")
    payload = {"session_id": session["session_id"], "graph": DEFAULT_GRAPH_CODEC.encode(graph),
        "explicit_secret_choices": choices, "receiver_lifecycle": {name: before[name] for name in names},
        **{"expected_" + name: before[name] for name in names[2:]},
        "idempotency_key": "installation-selected-graph"}
    metadata_before = len(provider.transport.calls)
    authored = await call("command.desired-graph.set", payload)
    assert len(provider.transport.calls) > metadata_before, "authoring bypassed provider metadata"
    assert all(method == "GET" and path.endswith("/metadata")
        for method, path in provider.transport.calls[metadata_before:])
    driver.reconstruct()
    state = await driver.workspace()
    assert state["desired_graph_id"] == authored["desired_graph_id"]
    assert state["desired_realized_projection_id"] == authored["desired_realized_projection_id"]
    assert state["desired_graph_revision"] == before["desired_graph_revision"] + 1
    assert state["current_graph_id"] == before["current_graph_id"]
    assert state["current_realized_projection_id"] == before["current_realized_projection_id"]
    readback = await call("read.desired-graph", {}, role=Role.READS)
    assert readback["graph_id"] == authored["desired_graph_id"]
    assert readback["realized_projection_id"] == authored["desired_realized_projection_id"]
    # Public graph projections intentionally redact selections. A read-only
    # test assertion checks the actual persisted source; never write the store
    # or reinterpret the public projection as round-trip authoring input.
    with schema.unit_of_work() as uow:
        stored = uow.stores.graphs.get(authored["desired_graph_id"])
        assert DEFAULT_GRAPH_CODEC.decode(stored.graph_descriptor) == selected, \
            "normal authoring did not persist the exact selected installation"
    metadata_after = len(provider.transport.calls)
    replay = await call("command.desired-graph.set", payload)
    assert replay == {**authored, "replayed": True} and authored["replayed"] is False
    assert len(provider.transport.calls) == metadata_after, "authoring replay reread provider metadata"
    assert metadata_after - metadata_before == sum(len(node.secret_selections)
        for node in selected.nodes.values())
    password = next(value for value in selections if value.reference == original.postgres_password)
    for node_id in (original.postgres_node_id, original.cpk_node_id):
        assert password in selected.node(node_id).secret_selections
    assert len(selected.nodes) == 8 and len(selected.public_ingresses) == 3
    assert all(type(value) is SecretVersionSelection for node in selected.nodes.values()
        for value in node.secret_selections)
    postgres = selected.node(original.postgres_node_id)
    assert postgres.block_spec.verification == graph.node(postgres.node_id).block_spec.verification
    fixture.selected_graph = selected
    fixture.secret_version_choices = choices
    return dict(evidence="real-isolated-selected-graph-registration-only",
        desired_graph_id=authored["desired_graph_id"],
        desired_realized_projection_id=authored["desired_realized_projection_id"],
        desired_graph_revision=state["desired_graph_revision"],
        postgres_image=image.execution_reference,
        postgres_product_descriptor_sha256=postgres.metadata["product_descriptor_digest"],
        installation_selections=[value.descriptor() for value in selections],
        metadata_observations=metadata_after - metadata_before,
        authoring_replayed=True, node_count=8, ingress_count=3)


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
    options = image_options(os.environ)
    image = options["images"]["postgres"] if "images" in options else options["postgres_image"]
    previous = Path.cwd()
    with TemporaryDirectory(prefix="cpk163-commission-") as directory:
        root = Path(directory)
        try:
            os.chdir(root)
            custody = root / "commissioning"
            custody.mkdir(mode=0o700)
            fixture, original, _, graph, gateway_document, _ = assemble(
                commissioning_directory=custody, **options)
            provider_id = PROVIDER if image is None else original.postgres_password.provider_id.value
            rows = signing_inputs(fixture, original, graph, custody, provider_id=provider_id)
            intents = {row["intent"].value for row in rows}
            if image is not None:
                intents.update(value.intent.value for node in graph.nodes.values() for value in node.secret_selections)
            intents = tuple(sorted(intents))
            with ProtectedProvider(workspace_id=original.workspace_id, provider_id=provider_id,
                    write_intents=intents, resolve_intents=intents) as provider, \
                    IsolatedOperationsSchema(database, "cpk_1912_" + uuid4().hex) as schema, \
                    patch("docker.DockerClient", side_effect=AssertionError("registration entered Docker effects")), \
                    patch("docker.from_env", side_effect=AssertionError("registration entered ambient Docker")):
                result = asyncio.run(commission(schema, root, fixture, original, graph, gateway_document, rows, provider,
                    selected_image=image))
                if "images" in options:
                    result["selected_images"] = {role:value.execution_reference
                        for role, value in options["images"].items()}
                if image is None:
                    assert not provider.transport.calls, "this stage unexpectedly resolved through an Operations execution"
        finally:
            os.chdir(previous)
    assert not root.exists(), "owned commissioning custody remains"
    if image is not None:
        assert result.get("evidence") == "real-isolated-selected-graph-registration-only", \
            "immutable image input did not commission the same selected installation graph"
    result["cleanup"] = "provider and commissioning directories removed; isolated schema dropped"
    result["source_imports"] = imports
    result["secrets_source_revision"] = os.environ["CPK_SOURCE_SECRETS_REVISION"]
    result["operations_database"] = "owned PostgreSQL test service; not the child SQL target"
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
