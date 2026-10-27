"""Actual factory and HTTP/MCP enrollment over the existing isolated Postgres owner."""
from dataclasses import replace
import json
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

from control_plane_kit_core.identity import AuthenticatedPrincipal, PrincipalIdentity, PrincipalKind, WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations.managed_runtime_assignments import ManagedRuntimeCapabilityPolicy
from control_plane_kit_operations.workflows import IdempotencyKey
from control_plane_kit_operations.workspace_permissions import (
    WorkspaceAdministrationContext, WorkspaceAdministrationPolicy, WorkspacePermissionCommandService,
)
from control_plane_kit_servers_cpk_server import server
from control_plane_kit_servers_cpk_server.authentication import (
    StaticDevelopmentMultiCredentialVerifier, StaticDevelopmentPrincipalCredential,
)

from cpk_http_host_fixtures import fixture
from receiver_acceptance_operations import IsolatedOperationsSchema, utc_now
from test_secret_provider_bootstrap import _base_environment


def workspace_authority_acceptance(database_url):
    from control_plane_kit_servers_cpk_server.operations_application import WorkspaceAuthorityConfiguration

    administrator = PrincipalIdentity("urn:cpk:enrollment", "administrator", PrincipalKind.OPERATOR)
    operator = PrincipalIdentity("urn:cpk:enrollment", "operator", PrincipalKind.OPERATOR)
    other_issuer = replace(operator, issuer="urn:cpk:other-issuer")
    other_kind = replace(operator, kind=PrincipalKind.WORKER)
    known = (administrator, operator, other_issuer, other_kind)
    policy = WorkspaceAdministrationPolicy("enrollment-installation", (administrator,), known)
    authority = WorkspaceAuthorityConfiguration(policy, ManagedRuntimeCapabilityPolicy(policy.installation_id, ()))
    credentials = ("synthetic-enrollment-admin", "synthetic-enrollment-operator",
        "synthetic-enrollment-other-issuer", "synthetic-enrollment-other-kind")
    # A startup grant must not bypass a missing/revoked durable dynamic grant.
    verifier = StaticDevelopmentMultiCredentialVerifier(tuple(
        StaticDevelopmentPrincipalCredential(token.encode(), AuthenticatedPrincipal(identity,
            () if identity == administrator else (WorkspaceGrant("workspace-b", (PolicyScope.INSTANCE_WORKSPACE_READ,)),)))
        for token, identity in zip(credentials, known, strict=True)))
    control = fixture("enrollment-root-bootstrap").config

    with IsolatedOperationsSchema(database_url, "cpk_1912_" + uuid4().hex) as schema:
        scoped_url = make_conninfo(database_url, options=f"-csearch_path={schema.schema}")
        environment = {**_base_environment(), "CPK_RUNTIME_INTERPRETERS": "none"}
        for name in tuple(environment):
            if name.endswith("_DATABASE_URL"):
                environment[name] = scoped_url
        config = replace(server.CpkServerBootstrapConfiguration.from_environment(environment),
            workspace_authority=authority)

        def require_startup_refusal(value):
            with patch.object(server, "_secret_provider_composition") as provider:
                with TestCase().assertRaises(server.BootstrapConfigurationError):
                    server.create_app(value, verifier, control=control, clock=lambda: 150)
                provider.assert_not_called()

        require_startup_refusal(config)
        # Explicit fixture initialization through the existing owner; startup never does this.
        initialized = WorkspacePermissionCommandService(schema.unit_of_work, administration_policy=policy,
            clock=utc_now, id_factory=lambda: uuid4().hex).initialize(
                WorkspaceAdministrationContext(administrator, policy.installation_id),
                idempotency_key=IdempotencyKey("initialize-enrollment-fixture"))
        assert not initialized.replayed
        other_policy = replace(policy, installation_id="other-installation")
        require_startup_refusal(replace(config, workspace_authority=WorkspaceAuthorityConfiguration(
            other_policy, ManagedRuntimeCapabilityPolicy(other_policy.installation_id, ()))))

        app = server.create_app(config, verifier, control=control, clock=lambda: 150)
        responses = []

        def invoke(client, surface, route_id, payload=None, *, token=credentials[0], workspace="workspace-b", status=200):
            route = app.state.http_boundary.composition.http_api.route(route_id)
            payload = {} if payload is None else dict(payload)
            headers = {"Authorization": "Bearer " + token}
            if surface == "http":
                location = route.path_template.replace("{workspace_id}", workspace)
                if route.method.value == "GET":
                    query = {key: json.dumps(value) if isinstance(value, dict) else value
                        for key, value in payload.items()}
                    response = client.get(location, params=query, headers=headers)
                else:
                    response = client.post(location, json=payload, headers=headers)
            else:
                read = route.method.value == "GET"
                bindings = (app.state.http_boundary.composition.handoff.projection_parity.projections if read
                    else app.state.http_boundary.composition.handoff.command_parity.commands)
                name = next(binding.mcp_tool_name for binding in bindings if binding.http_route_id == route_id)
                method = "resources/read" if read else "tools/call"
                if "{workspace_id}" in route.path_template:
                    payload = {"workspace_id": workspace, **payload}
                response = client.post("/mcp", headers={**headers, "Accept": "application/json",
                    "MCP-Protocol-Version": "2025-06-18", "Mcp-Method": method}, json={
                    "jsonrpc": "2.0", "id": "enrollment", "method": method,
                    "params": {"name": name, "arguments": payload}})
            assert response.status_code == status, (route_id, surface, response.status_code)
            result = response.json()
            assert all(secret not in json.dumps(result) for secret in credentials)
            responses.append(result)
            return result["result"] if surface == "mcp" and status == 200 else result

        with TestClient(app) as client:
            for surface, workspace in (("http", "workspace-a"), ("mcp", "workspace-b")):
                invoke(client, surface, "command.workspace-administration.create", {
                    "workspace_id": workspace, "name": workspace, "idempotency_key": "create-" + workspace})
            for surface in ("http", "mcp"):
                invoke(client, surface, "read.current-graph", token=credentials[1], status=403)
                invoke(client, surface, "command.workspace-administration.create", {
                    "workspace_id": "denied-workspace", "name": "Denied", "idempotency_key": "denied-create"},
                    token=credentials[1], status=403)
            grant = {"target": operator.descriptor(), "scopes": [PolicyScope.INSTANCE_WORKSPACE_READ.value],
                "expected_revision": 0, "idempotency_key": "grant-workspace-b"}
            invoke(client, "http", "command.workspace-permission.grant", grant)
            assert invoke(client, "mcp", "command.workspace-permission.grant", grant)["replayed"]
            invoke(client, "http", "command.workspace-permission.grant",
                {**grant, "idempotency_key": "conflicting-grant"}, status=409)
            for surface in ("http", "mcp"):
                invoke(client, surface, "read.current-graph", token=credentials[1])
                invoke(client, surface, "read.current-graph", token=credentials[1], workspace="workspace-a", status=403)
                for token in credentials[2:]:
                    invoke(client, surface, "read.current-graph", token=token, status=403)
            record = invoke(client, "http", "read.workspace-permission", {"target": operator.descriptor()})
            assert record["revision"] == 1 and record["scopes"] == grant["scopes"]
            invoke(client, "mcp", "command.workspace-permission.revoke", {"target": operator.descriptor(),
                "expected_revision": record["revision"], "idempotency_key": "revoke-workspace-b"})
            for surface in ("http", "mcp"):
                invoke(client, surface, "read.current-graph", token=credentials[1], status=403)

        # Reconstruct through the real startup/factory without rewriting the verifier or receipt.
        restarted = server.create_app(config, verifier, control=control, clock=lambda: 150)
        with TestClient(restarted) as client:
            for surface in ("http", "mcp"):
                invoke(client, surface, "read.current-graph", token=credentials[1], status=403)
            record = invoke(client, "http", "read.workspace-permission", {"target": operator.descriptor()})
            assert record["revision"] == 2 and record["scopes"] == []
        assert len(responses) < 50
    print("workspace authority: real startup receipt, public grant/revoke, full identity and restart preservation passed", flush=True)
