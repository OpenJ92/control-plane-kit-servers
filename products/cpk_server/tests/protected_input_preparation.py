"""Actual authenticated host -> durable Operations -> encrypted provider -> preparation.

Executed only by the existing normal smoke controller. The sole substituted
production port is provider HTTP transport; no service, receipt or store is fake.
"""
import base64
import json
from unittest.mock import patch
from urllib.parse import quote
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg.conninfo import make_conninfo
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
from control_plane_kit_servers_cpk_server import server

from cpk_http_host_fixtures import fixture
from protected_input_graph import authored_graph, declared_documents
from protected_input_provider import INTENTS, MATERIAL, PROVIDER, PURPOSES, TOKEN, WORKSPACE, ProtectedProvider, protected_file
from receiver_acceptance_operations import IsolatedOperationsSchema, utc_now
from test_secret_provider_bootstrap import _provider_environment


OPERATOR = "synthetic-input-operator"
VIEWER = "synthetic-input-viewer"
WORKER = "synthetic-input-worker"
REGISTER_ONLY = "synthetic-input-register-only"
PROVISION_ONLY = "synthetic-input-provision-only"
GENERATE_ONLY = "synthetic-input-generate-only"
INTAKE = "command.secret-material.provision"


def principal_configuration():
    # Preparation authority deliberately omits approval, execution, and revocation.
    operator = tuple(getattr(PolicyScope, name) for name in (
        "HUB_INSTANCE_CREATE", "INSTANCE_WORKSPACE_READ", "INSTANCE_WORKSPACE_EDIT", "PLAN_REQUEST",
        "RUNTIME_AUTHORITY_REGISTER", "RUNTIME_AUTHORITY_READ", "RUNTIME_AUTHORITY_USE",
        "INGRESS_AUTHORITY_REGISTER", "INGRESS_AUTHORITY_READ", "INGRESS_AUTHORITY_USE",
        "SECRET_PROVIDER_REGISTER", "SECRET_PROVIDER_READ", "SECRET_PROVIDER_USE", "SECRET_MATERIAL_PROVISION",
        "DELEGATION_KEY_GENERATE", "DELEGATION_KEY_REGISTER", "DELEGATION_KEY_READ", "DELEGATION_KEY_ACTIVATE",
        "DELEGATION_KEY_USE"))
    return [{"credential": token, "subject_id": subject, "kind": kind,
             "workspace_grants": {WORKSPACE: [scope.value for scope in scopes]}}
        for token, subject, kind, scopes in (
            (OPERATOR, "input-operator", "operator", operator),
            (VIEWER, "input-viewer", "operator", (PolicyScope.INSTANCE_WORKSPACE_READ, PolicyScope.SECRET_PROVIDER_READ)),
            (WORKER, "input-worker", "worker", (PolicyScope.SECRET_MATERIAL_PROVISION,
                PolicyScope.SECRET_PROVIDER_REGISTER, PolicyScope.PLAN_EXECUTE, PolicyScope.EXECUTION_OPERATE)),
            (REGISTER_ONLY, "input-register", "operator", (PolicyScope.SECRET_PROVIDER_REGISTER, PolicyScope.DELEGATION_KEY_REGISTER)),
            (PROVISION_ONLY, "input-provision", "operator", (PolicyScope.SECRET_MATERIAL_PROVISION,)),
            (GENERATE_ONLY, "input-generate", "operator", (PolicyScope.DELEGATION_KEY_GENERATE,)),
        )]


class AuthenticatedHost:
    """Bounded credential-bearing HTTP calls, retaining public responses only."""
    def __init__(self, app, client):
        self.app, self.client, self.responses = app, client, []

    def call(self, route_id, payload=None, *, path=None, credential=OPERATOR, status=200):
        route = self.app.state.http_boundary.composition.http_api.route(route_id)
        location = route.path_template
        for name, value in {"workspace_id": WORKSPACE, **(path or {})}.items():
            location = location.replace("{" + name + "}", quote(str(value), safe=""))
        assert "{" not in location, "missing public route coordinate"
        kwargs = {"headers": {"Authorization": "Bearer " + credential}}
        if route.method.value == "GET":
            kwargs["params"] = payload or {}
        else:
            kwargs["json"] = {} if payload is None else payload
        response = self.client.request(route.method.value, location, **kwargs)
        # Never include submitted bodies or credentials in an assertion message.
        assert response.status_code == status, (route_id, response.status_code, status)
        assert len(response.content) <= 2_097_152, "public response exceeded witness bound"
        value = response.json()
        self.record(value)
        return value

    def record(self, value):
        encoded = json.dumps(value, sort_keys=True)
        for forbidden in (MATERIAL, base64.b64encode(MATERIAL.encode()).decode(), TOKEN,
                OPERATOR, VIEWER, WORKER, REGISTER_ONLY, PROVISION_ONLY, GENERATE_ONLY, "PRIVATE KEY"):
            assert forbidden not in encoded, "sensitive input appeared in public output"
        assert len(self.responses) < 100, "public observation budget exceeded"
        self.responses.append(value)


def protected_input_preparation(database_url):
    documents = declared_documents()
    with IsolatedOperationsSchema(database_url, "cpk_1912_" + uuid4().hex) as schema, ProtectedProvider() as provider:
        # Same schema-only option as the existing lifecycle owner, through libpq's encoder.
        scoped_url = make_conninfo(database_url, options=f"-csearch_path={schema.schema}")
        with psycopg.connect(scoped_url) as connection:
            assert connection.execute("SELECT current_schema()").fetchone() == (schema.schema,)
        managed_path = provider.root / "managed.json"
        protected_file(managed_path, json.dumps({"schema": "cpk-server.managed-health.v1",
            "docker": {"socket_path": str(provider.root / "never-created-docker.sock"), "request_timeout": 5.0},
            "scopes": [{"workspace_id": WORKSPACE, "runtime_id": "docker", "authority_ref": "local-docker"}],
            "gateway_documents": [documents["gateway"].content.decode()],
            "native_product_document": documents["connector"].content.decode()}))
        environment = {**_provider_environment(provider.token_file),
            "CPK_INGRESS_INTERPRETERS": "cloudflare",
            "CPK_CONTROL_AUTH_VERIFIER": "static-development",
            "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON": json.dumps(principal_configuration()),
            "CPK_MATERIAL_PROVIDER_ROUTES_JSON": json.dumps({PROVIDER: "https://input-provider.invalid"}),
            "CPK_MANAGED_HEALTH": "docker-unix-v1", "CPK_MANAGED_HEALTH_CONFIGURATION_FILE": str(managed_path)}
        for name in tuple(environment):
            if name.endswith("_DATABASE_URL"):
                environment[name] = scoped_url
        config = server.CpkServerBootstrapConfiguration.from_environment(environment)
        assert config.operations_database_url() == scoped_url
        real_provider = server._secret_provider_composition
        def compose(configuration):
            return real_provider(configuration, transport=provider.transport)
        # Only provider delivery changes. Host authentication, factory, UoW, and owners stay real.
        with patch.object(server, "_secret_provider_composition", side_effect=compose):
            app = server.create_app(config, server._credential_verifier(config),
                control=fixture("input-root-bootstrap").config,
                principal_authorizer=server._configured_principal_authorizer(config))
        assert provider.transport.calls == []
        with TestClient(app) as client:
            host = AuthenticatedHost(app, client)
            exercise(host, provider, documents)
    print("protected input: real authenticated generation/custody, reference-only preparation and owned cleanup passed", flush=True)


def exercise(host, provider, documents):
    host.call("command.workspace.create", {"workspace_id": WORKSPACE,
        "name": "Protected input preparation", "idempotency_key": "input-workspace"})
    initial = host.call("read.receiver-authoring-context")
    assert initial["desired"] is None and initial["current"]["receivers"] == []
    instant = utc_now()
    registration = host.call("command.secret-provider.register", {
        "provider_id": PROVIDER, "display_name": "Test-owned encrypted custody",
        "provider_kind": "control-plane-kit-secrets", "endpoint_reference": PROVIDER,
        "credential_reference": "secret://bootstrap/provider-token",
        "allowed_reference_prefixes": ["secret://input-provider/material", "secret://input-provider/keys",
            "secret://input-provider/generated"],
        "allowed_intents": [*INTENTS, "cloudflare.api-token", "cloudflare.tunnel-token"],
        "admitted_at": instant, "metadata": {}, "idempotency_key": "input-provider"})
    generation = {"request_id": "generate-0", "provider_registration_id": registration["registration_id"],
        "secret_reference": "secret://input-provider/keys/key-0", "purpose": PURPOSES[0].value, "issuer": "cpk-server"}
    provision = {"request_id": "provision-token", "provider_registration_id": registration["registration_id"],
        "secret_reference": "secret://input-provider/material/api-token", "intent": "cloudflare.api-token",
        "value_base64": base64.b64encode(MATERIAL.encode()).decode()}
    before = (tuple(provider.transport.calls), provider.audit.rows_for_tests())
    for credential, status in (("invalid-credential", 401), (VIEWER, 403), (WORKER, 403),
                               (REGISTER_ONLY, 403), (PROVISION_ONLY, 403)):
        host.call(INTAKE, provision, credential=credential, status=status)
    for credential in (REGISTER_ONLY, GENERATE_ONLY):
        host.call("command.delegation-key.generate", generation, credential=credential, status=403)
    # HTTP-only provision remains uncallable by MCP even with valid operator authority.
    response = host.client.post("/mcp", headers={"Authorization": "Bearer " + OPERATOR,
        "Accept": "application/json", "MCP-Protocol-Version": "2025-06-18", "Mcp-Method": "tools/call"},
        json={"jsonrpc": "2.0", "id": "protected-refusal", "method": "tools/call",
              "params": {"name": INTAKE, "arguments": {"workspace_id": WORKSPACE, **provision}}})
    assert response.status_code == 400
    host.record(response.json())
    response = host.client.post(f"/workspaces/{WORKSPACE}/secret-material/provision",
        headers={"Authorization": "Bearer " + OPERATOR}, content=b" " * 98_305)
    assert response.status_code == 413
    host.record(response.json())
    assert (tuple(provider.transport.calls), provider.audit.rows_for_tests()) == before
    generated = []
    for number, purpose in enumerate(PURPOSES):
        result = host.call("command.delegation-key.generate", {**generation,
            "request_id": f"generate-{number}", "secret_reference": f"secret://input-provider/keys/key-{number}",
            "purpose": purpose.value})
        assert result["state"] == "admitted" and result["admission"]
        receipt = result["receipt"]
        assert receipt["version_id"] and receipt["version_number"] == 1
        assert host.call("read.delegation-key-generation", path={"request_id": f"generate-{number}"}) == result
        host.call("command.delegation-key.activate", {"purpose": purpose.value, "issuer": "cpk-server",
            "key_id": receipt["public_key"]["key_id"], "activated_at": utc_now(), "idempotency_key": f"activate-{number}"})
        generated.append(result)
    admitted = host.call(INTAKE, provision)
    assert admitted["state"] == "admitted" and admitted["custody"]["version_number"] == 1
    assert admitted["admission"]["reference_id"] == provision["secret_reference"]
    assert len(provider.transport.calls) == 4 and provider.audit.rows_for_tests()
    assert all(method == "POST" for method, _ in provider.transport.calls)
    assert sum(path.endswith("/generate") for _, path in provider.transport.calls) == 3
    before = (tuple(provider.transport.calls), provider.audit.rows_for_tests())
    conflict = host.call(INTAKE, provision, status=409)
    navigation = conflict["error"]["status_reference"]
    assert navigation == {"route_id": "read.secret-material-provision", "workspace_id": WORKSPACE,
                          "request_id": provision["request_id"]}
    host.call(navigation["route_id"], path=navigation, credential=PROVISION_ONLY, status=403)
    status = host.call(navigation["route_id"], path=navigation, credential=VIEWER)
    assert status == admitted
    assert (tuple(provider.transport.calls), provider.audit.rows_for_tests()) == before
    prepare(host, documents, generated, admitted, registration["registration_id"])
    # Provider reads may supplement preparation, but no secret resolution/revocation is authorized.
    assert not any("resolve" in path or "revoke" in path for _, path in provider.transport.calls)
    host.record(provider.audit.rows_for_tests())


def prepare(host, documents, generated, admitted, provider_registration_id):
    context = host.call("read.receiver-authoring-context")
    verifiers = host.call("read.workload-verifier-configuration",
        path={"purposes": ",".join(purpose.value for purpose in PURPOSES[:2])})
    public_verifiers = json.dumps(verifiers)
    for result in generated[:2]:
        assert result["receipt"]["public_key"]["key_id"] in public_verifiers
    graph, documents, configurations = authored_graph(documents, context, verifiers, generated[2]["receipt"]["public_key"])
    instant = utc_now()
    host.call("command.runtime-authority.register", {"authority_ref": "local-docker", "runtime_kind": "docker",
        "authority": {"kind": "local-docker-socket"}, "admitted_at": instant, "idempotency_key": "input-runtime"})
    host.call("command.ingress-authority.register", {"authority_ref": "zone",
        "authority": {"provider_kind": "cloudflare", "account_id": "synthetic-account", "zone_id": "synthetic-zone",
            "zone_name": "example.invalid", "api_token_ref": admitted["admission"]["reference_id"],
            "allowed_hostname_pattern": "cpk-input.example.invalid",
            "generated_secret_provider_registration_id": provider_registration_id,
            "generated_secret_reference_prefix": "secret://input-provider/generated"},
        "admitted_at": instant, "idempotency_key": "input-ingress"})
    for name, document in documents.items():
        host.call("command.product.import", {"descriptor_document": json.loads(document.content),
            "imported_at": instant, "idempotency_key": "input-product-" + name})
    before = host.call("read.workspace")["workspace"]
    encoded = DEFAULT_GRAPH_CODEC.encode(graph)
    host.record(encoded)
    prepared = host.call("command.deployment.prepare", {"desired_graph": encoded,
        "expected_current": {"authored_graph_id": before["current_graph_id"],
            "realized_projection_id": before["current_realized_projection_id"]},
        "expected_desired": None, "expected_desired_graph_revision": before["desired_graph_revision"],
        "title": "Protected input preparation", "idempotency_key": "input-prepare"})
    assert prepared["status"] == "approval-required"
    host.call("command.approval.decide", {}, path={"approval_id": prepared["approval_request_id"]}, status=403)
    host.call("command.deployment.execute", {}, path={"run_id": "never-admitted"}, status=403)
    plan = host.call("read.plan-detail", path={"plan_id": prepared["plan_id"]})["plan"]
    host.call("read.session-detail", path={"session_id": plan["session_id"]})
    runs = host.call("read.plan-runs", {"limit": 100}, path={"plan_id": prepared["plan_id"]})
    assert runs["items"] == [] and runs["next_cursor"] is None
    after = host.call("read.receiver-authoring-context")
    receivers = {item["binding"]["node_id"]: item["binding"]["receiver_id"] for item in after["desired"]["receivers"]}
    assert receivers == {name: config.target.receiver_id for name, config in configurations.items()}
    current = host.call("read.workspace")["workspace"]
    assert current["current_graph_id"] == before["current_graph_id"]
    assert current["current_realized_projection_id"] == before["current_realized_projection_id"]
