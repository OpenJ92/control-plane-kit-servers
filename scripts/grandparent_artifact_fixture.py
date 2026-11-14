"""Disposable normal-process witness through real HTTP/MCP and Operations owners.

Only bootstrap initializes the new fixture installation directly. Thereafter
all graph, permission, planning and history actions use authenticated HTTP.
Never use these synthetic files or identities with an existing installation.
"""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import quote
from uuid import uuid4

WORKSPACE = "workspace-a"
INSTALLATION = "cpk399-isolated-mcp"
ISSUER = "urn:control-plane-kit:static-development"
BOUND = 1_048_576
STEPS = frozenset(("fixture", "generate", "initialize", "readiness", "workspace-create",
    "grant-setup", "grant-reader", "session-start", "draft-create", "workspace-before-select",
    "draft-select", "workspace-selected", "managed-prepare", "workspace-preserved",
    "preparation-history", "plan-detail", "managed-replay", "history-preserved", "save-revision",
    "saved-fixture", "attempt-history", "http-denial", "mcp-denial", "mcp-discovery",
    "mcp-protocol", "mcp-command-denial", "get_workspace", "get_desired_graph",
    "get_desired_topology_draft_revision", "list_desired_topology_draft_revision_attempts"))
CATEGORIES = frozenset(("transport", "http-status", "body-bound", "redaction", "json",
    "shape", "assertion", "readiness-timeout", "local-fixture", "unexpected"))


class WitnessFailure(Exception):
    def __init__(self, category, http_status=None):
        super().__init__("isolated witness failed")
        self.category, self.http_status = category, http_status


def failure_record(mode, step, category, http_status=None):
    """Only closed labels and a validated number may cross the log boundary."""
    return dict(schema="cpk399.witness-diagnostic.v1",
        mode=mode if mode in {"generate", "initialize", "seed", "verify"} else "invalid",
        step=step if step in STEPS else "fixture",
        category=category if category in CATEGORIES else "unexpected",
        http_status=http_status if type(http_status) is int and 100 <= http_status <= 599 else None)


if not __debug__:
    raise SystemExit("isolated witness requires enabled checks")


def write(directory, name, value, *, public=False):
    content = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o444 if public else 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)


def generate(directory):
    from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
    from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference, ProductReferenceCodec
    from control_plane_kit_core.secrets import SecretFileDelivery, SecretFilePathBinding
    from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import gateway_http_sample_declared_runtime_contract
    from control_plane_kit_servers_cpk_server.control_configuration import cpk_control_configuration_artifact
    from cpk_http_host_fixtures import fixture
    from managed_native_material import NativeMaterial

    administrator = PrincipalIdentity(ISSUER, "setup", PrincipalKind.OPERATOR)
    reader = PrincipalIdentity(ISSUER, "reader", PrincipalKind.OPERATOR)
    actors = {name: secrets.token_urlsafe(32) for name in ("setup", "reader")}
    material = NativeMaterial()
    codec = ProductDescriptorCodec()
    gateway = codec.encode_document(replace(material.authored.documents["gateway"].product,
        runtime_contract=gateway_http_sample_declared_runtime_contract()))
    postgres = codec.decode_document(Path("/witness/postgres.json").read_bytes())
    delivery, = postgres.product.runtime_contract.secret_deliveries
    # Public descriptor adaptation only; no PostgreSQL credential or material
    # operation is performed for this never-deployed descriptor.
    contract = replace(postgres.product.runtime_contract, secret_deliveries=(SecretFileDelivery(
        "/run/secrets/postgres-password", delivery.reference, delivery.intent,
        path_binding=SecretFilePathBinding("POSTGRES_PASSWORD_FILE")),))
    postgres = codec.encode_document(replace(postgres.product, runtime_contract=contract))
    authority = dict(schema="cpk-server.workspace-authority.v1", installation_id=INSTALLATION,
        administrators=[administrator.descriptor()], known_identities=[administrator.descriptor(), reader.descriptor()],
        capabilities=["isolated-docker"])
    health = dict(schema="cpk-server.managed-health.v2",
        docker=dict(socket_path="/var/run/cpk399-unavailable.sock", request_timeout=2.0),
        capability_ids=["isolated-docker"], gateway_documents=[gateway.content.decode()],
        native_product_document=material.document.content.decode())
    sender = dict(schema="cpk-server.managed-verification.v1",
        gateway_product=ProductReferenceCodec().encode(ProductReference.from_document(gateway)),
        postgres_product_document=postgres.content.decode())
    receiver = cpk_control_configuration_artifact(fixture("cpk399").config)
    for name, value in (("authority.json", authority), ("health.json", health),
            ("sender.json", sender), ("control.json", receiver.content)):
        write(directory, name, value, public=True)
    write(directory, "actors.json", actors)
    environment = dict(CPK_SERVER_MODE="execution-capable", CPK_PORT="8080",
        CPK_MCP_PROFILE="grandparent-read-only-v1", CPK_RUNTIME_INTERPRETERS="docker",
        CPK_CONTROL_AUTH_VERIFIER="static-development",
        CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON=json.dumps([
            dict(credential=actors[identity.subject_id], subject_id=identity.subject_id,
                kind=identity.kind.value, workspace_grants={}) for identity in (administrator, reader)]),
        CPK_WORKSPACE_AUTHORITY="dynamic-v1",
        CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE="/fixture/authority.json",
        CPK_MANAGED_HEALTH="docker-unix-v2",
        CPK_MANAGED_HEALTH_CONFIGURATION_FILE="/fixture/health.json",
        CPK_MANAGED_VERIFICATION_CONFIGURATION_FILE="/fixture/sender.json",
        CPK_PRODUCT_MATERIAL_RESOLVER="provider",
        CPK_MATERIAL_PROVIDER_ROUTES_JSON=json.dumps({"fixture-provider": "http://provider.invalid"}),
        CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON=json.dumps({
            "secret://fixture/provider-token": "/run/secrets/not-provided"}))
    for name in ("WORKPLACE", "ACTIVITY_HISTORY", "OBSERVER_STATE", "GRAPH_TOPOLOGY"):
        environment["CPK_" + name + "_DATABASE_URL"] = "postgresql://cpk:cpk@database:5432/cpk"
    assert all("\n" not in value and "\r" not in value for value in environment.values())
    write(directory, "server.env", "".join(key + "=" + value + "\n" for key, value in environment.items()))
    write(directory, "public-inputs.json", {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in ("authority.json", "health.json", "sender.json", "control.json")}, public=True)


def initialize():
    import psycopg
    from control_plane_kit_operations.postgres import PostgresUnitOfWork
    from control_plane_kit_operations.workflows import IdempotencyKey
    from control_plane_kit_operations.workspace_permissions import WorkspaceAdministrationContext, WorkspacePermissionCommandService
    from control_plane_kit_servers_cpk_server import server
    config = server.CpkServerBootstrapConfiguration.from_environment()
    assert config.mcp_profile == "grandparent-read-only-v1"
    assert config.managed_verification_support is not None and config.http_sample_support is not None
    policy = config.workspace_authority.administration_policy
    database = config.operations_database_url()
    server._install_operations_schema(database)
    service = WorkspacePermissionCommandService(lambda: PostgresUnitOfWork(lambda: psycopg.connect(database)),
        administration_policy=policy, clock=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        id_factory=lambda: uuid4().hex)
    receipt = service.initialize(WorkspaceAdministrationContext(policy.administrators[0], policy.installation_id),
        idempotency_key=IdempotencyKey("isolated-bootstrap"))
    assert not receipt.replayed


class Witness:
    def __init__(self, directory):
        self.step = "fixture"
        self.directory = directory
        self.actors = json.loads((directory / "actors.json").read_text())
        # The helper shares only the candidate's network namespace. The product
        # has no published port; the MCP host sees the same loopback authority
        # as its ordinary installed-client contract.
        self.base = "http://127.0.0.1:8080"

    async def request(self, path, payload=None, *, actor="setup", expected=200, step=None):
        import httpx2
        if step is not None:
            self.step = step if step in STEPS else "fixture"
        headers = {} if actor is None else {"Authorization": "Bearer " + self.actors.get(actor, "incorrect")}
        failure, value = None, None
        try:
            async with httpx2.AsyncClient(timeout=10, trust_env=False, headers=headers) as client:
                async with client.stream("GET" if payload is None else "POST", self.base + path, json=payload) as response:
                    if response.status_code != expected:
                        failure = WitnessFailure("http-status", response.status_code)
                    else:
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > BOUND:
                                failure = WitnessFailure("body-bound")
                                break
                            body.extend(chunk)
                        if failure is None and any(token.encode() in body for token in self.actors.values()):
                            failure = WitnessFailure("redaction")
                        if failure is None:
                            try:
                                value = json.loads(body)
                            except (UnicodeDecodeError, ValueError):
                                failure = WitnessFailure("json")
                            if failure is None and type(value) is not dict:
                                failure = WitnessFailure("shape")
        except httpx2.TransportError:
            failure = WitnessFailure("transport")
        if failure is not None:
            raise failure
        return value

    async def ready(self):
        for _ in range(30):
            try:
                value = await self.request("/health/ready", actor=None, step="readiness")
                if any(value.get(key) != expected for key, expected in (
                        ("status", "ready"), ("application", "configured"), ("stores", "configured"))):
                    raise WitnessFailure("shape")
                return
            except WitnessFailure as failure:
                if failure.category != "transport":
                    raise
                await asyncio.sleep(1)
        raise WitnessFailure("readiness-timeout")

    async def seed(self):
        await self.ready()
        await self.request("/administration/workspaces", dict(workspace_id=WORKSPACE,
            name="Isolated MCP witness", idempotency_key="create-workspace"), step="workspace-create")
        for actor, scopes in (("setup", ["instance:workspace:read", "instance:workspace:edit", "plan:request"]),
                ("reader", ["instance:workspace:read"])):
            await self.request("/workspaces/" + WORKSPACE + "/permissions/grant", dict(
                target=dict(issuer=ISSUER, subject_id=actor, kind="operator"), scopes=scopes,
                expected_revision=0, idempotency_key="grant-" + actor), step="grant-" + actor)
        session = await self.request("/workspaces/" + WORKSPACE + "/sessions", dict(
            title="Isolated saved revision", idempotency_key="session"), step="session-start")
        root = "/workspaces/" + WORKSPACE
        draft = await self.request(root + "/desired-topology-drafts", dict(session_id=session["session_id"],
            title="Read-only witness", idempotency_key="draft", graph=dict(name="isolated-empty",
                runtimes={}, nodes={}, edges={}, public_ingresses=[])), step="draft-create")
        path = root + "/desired-topology-drafts/" + quote(draft["draft_id"], safe="")
        before = (await self.request(root, step="workspace-before-select"))["workspace"]
        await self.request(path + "/select", dict(session_id=session["session_id"], revision=draft["revision"],
            idempotency_key="select", expected_desired_graph_id=before["desired_graph_id"],
            expected_desired_realized_projection_id=before["desired_realized_projection_id"],
            expected_desired_graph_revision=before["desired_graph_revision"]), step="draft-select")
        workspace = (await self.request(root, step="workspace-selected"))["workspace"]
        payload = dict(draft_id=draft["draft_id"], revision=draft["revision"],
            expected_current=dict(authored_graph_id=workspace["current_graph_id"],
                realized_projection_id=workspace["current_realized_projection_id"]),
            expected_desired=dict(authored_graph_id=workspace["desired_graph_id"],
                realized_projection_id=workspace["desired_realized_projection_id"]),
            expected_desired_graph_revision=workspace["desired_graph_revision"], title="Managed intent witness",
            idempotency_key="managed-http", managed_verification="authenticated-local-postgres-and-http")
        preparation = await self.request(root + "/deployments/prepare", payload, step="managed-prepare")
        # The empty graph deliberately cannot satisfy managed SQL/HTTP bootstrap.
        # The real planner must preserve that blocked result, never execute it.
        assert preparation["status"] == "review-blocked" and preparation["workspace_id"] == WORKSPACE
        plan_id = preparation["plan_id"]
        assert type(plan_id) is str and plan_id
        assert (await self.request(root, step="workspace-preserved"))["workspace"] == workspace
        revision_path = path + "/revisions/" + str(draft["revision"])
        history = await self.request(revision_path + "/preparations", step="preparation-history")
        assert history["items"], "real preparation history was not recorded"
        plan_path = root + "/plans/" + quote(plan_id, safe="")
        plan = (await self.request(plan_path, step="plan-detail"))["plan"]
        assert plan["derivation_profile"] == "managed-sql-http-bootstrap-v1"
        assert (plan["base_graph_id"], plan["base_realized_projection_id"], plan["desired_graph_id"],
            plan["desired_realized_projection_id"], plan["desired_graph_revision"]) == (
            workspace["current_graph_id"], workspace["current_realized_projection_id"], workspace["desired_graph_id"],
            workspace["desired_realized_projection_id"], workspace["desired_graph_revision"])
        # Known completed response, explicit fixture idempotency proof. Never
        # use this as recovery of an interrupted or ambiguous external effect.
        assert await self.request(root + "/deployments/prepare", payload, step="managed-replay") == preparation
        assert await self.request(revision_path + "/preparations", step="history-preserved") == history
        self.step = "save-revision"
        write(self.directory, "saved.json", dict(identity=dict(workspace_id=WORKSPACE,
            draft_id=draft["draft_id"], revision=draft["revision"]), workspace=workspace,
            preparation=preparation, history=history, revision_path=revision_path, prepare_payload=payload,
            plan=plan, plan_path=plan_path))

    async def verify(self):
        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
        await self.ready()
        self.step = "saved-fixture"
        saved = json.loads((self.directory / "saved.json").read_text())
        root = "/workspaces/" + WORKSPACE
        assert (await self.request(root, step="workspace-preserved"))["workspace"] == saved["workspace"]
        assert await self.request(saved["revision_path"] + "/preparations", step="history-preserved") == saved["history"]
        assert (await self.request(saved["plan_path"], step="plan-detail"))["plan"] == saved["plan"]
        assert (await self.request(saved["revision_path"] + "/attempts", step="attempt-history"))["items"] == []
        await self.request(root, actor=None, expected=401, step="http-denial")
        await self.request(root, actor="incorrect", expected=401, step="http-denial")
        self.step = "mcp-denial"
        async with httpx2.AsyncClient(timeout=10, trust_env=False) as unauthenticated:
            for headers in ({}, {"Authorization": "Bearer incorrect"}):
                response = await unauthenticated.post(self.base + "/mcp", headers=headers, content=b"{}")
                assert response.status_code == 401
        reads = {
            "get_workspace": (dict(workspace_id=WORKSPACE), root),
            "get_desired_graph": (dict(workspace_id=WORKSPACE), root + "/graphs/desired"),
            "get_desired_topology_draft_revision": (saved["identity"], saved["revision_path"]),
            "list_desired_topology_draft_revision_attempts": (saved["identity"], saved["revision_path"] + "/attempts")}
        for mode, protocol in (("auto", "2026-07-28"), ("legacy", "2025-11-25")):
            for actor in ("reader", "setup"):
                async with httpx2.AsyncClient(timeout=10, trust_env=False,
                        headers={"Authorization": "Bearer " + self.actors[actor]}) as http:
                    self.step = "mcp-protocol"
                    async with Client(streamable_http_client(self.base + "/mcp", http_client=http), mode=mode) as client:
                        assert client.protocol_version == protocol
                        self.step = "mcp-discovery"
                        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                        assert set(tools) == set(reads)
                        assert all(tool.annotations.read_only_hint for tool in tools.values())
                        for name, (arguments, path) in reads.items():
                            self.step = name
                            result = await client.call_tool(name, arguments)
                            assert not result.is_error
                            assert result.structured_content == await self.request(path, actor=actor)
                            assert all(value not in json.dumps(result.structured_content) for value in self.actors.values())
                        self.step = "mcp-command-denial"
                        refused = await client.call_tool("prepare_deployment", {"workspace_id": WORKSPACE, **saved["prepare_payload"]})
                        assert refused.is_error and refused.structured_content["error"]["status"] == 404
        assert await self.request(saved["revision_path"] + "/preparations", step="history-preserved") == saved["history"]
        assert (await self.request(root, step="workspace-preserved"))["workspace"] == saved["workspace"]
        print("isolated MCP: four reads/HTTP parity, both protocol eras, auth and command refusal, saved state/history preserved", flush=True)


def main():
    logging.disable(logging.CRITICAL)
    mode, witness, failure = "invalid", None, None
    try:
        assert len(sys.argv) == 3
        mode, directory = sys.argv[1], Path(sys.argv[2])
        if mode == "generate":
            generate(directory)
        elif mode == "initialize":
            initialize()
        elif mode in ("seed", "verify"):
            witness = Witness(directory)
            asyncio.run(getattr(witness, mode)())
        else:
            raise ValueError
    except Exception as error:
        category = (error.category if type(error) is WitnessFailure else
            "assertion" if isinstance(error, AssertionError) else
            "shape" if isinstance(error, (KeyError, TypeError)) else
            "local-fixture" if isinstance(error, (OSError, json.JSONDecodeError)) else "unexpected")
        failure = failure_record(mode, witness.step if witness is not None else mode,
            category, error.http_status if type(error) is WitnessFailure else None)
    if failure is not None:
        # Outside the exception handler: no request/body exception is rendered.
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
