"""Named child ingress through normal process configuration and the released MCP transport."""
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.secrets import (
    SecretEnvironmentDelivery, SecretFileDelivery, SecretFilePathBinding,
    SecretReference, SecretReferenceEnvironmentDelivery, SecretUseIntent,
)
from control_plane_kit_operations import CpkServerOperationsApplication, WorkspaceContextResolver
from control_plane_kit_operations.cpk_server import CpkServerReadService
from control_plane_kit_operations.records import WorkspaceRecord
from control_plane_kit_operations.workspace_permissions import WorkspacePermissionRecord

import test_installation_management as installations
from test_http_mcp_boundaries import RecordingService


HOST_SETTING = "CPK_MCP_CHILD_API_HOSTNAME"
INITIALIZE = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-11-25", "capabilities": {},
    "clientInfo": {"name": "child-api-test", "version": "1"}}}


class ChildMcpHostTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from control_plane_kit_servers_cpk_server import server
        self.server = server
        self.fixture = installations.InstallationManagementTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        api = self.fixture.api
        self.child = self.fixture.installation(website=self.fixture.managed_website(), workspace_grants=(),
            control_auth=api.MultiPrincipalControlAuth(SecretReference("secret://fixture/principals")),
            workspace_authority=api.SuppliedChildWorkspaceAuthority(SecretReference("secret://fixture/policy")))
        self.graph = self.fixture.graph(self.child)
        self.node = self.graph.node(self.child.cpk_node_id)
        self.hostname = self.child.ingress.hostname

    def test_only_named_supplied_child_cpk_receives_the_composer_owned_host(self):
        self.assertEqual(self.node.non_secret_environment().get(HOST_SETTING), self.hostname)
        for node in self.graph.nodes.values():
            if node.node_id != self.node.node_id:
                self.assertNotIn(HOST_SETTING, node.non_secret_environment())
        external_child = replace(self.fixture.base, workspace_grants=(),
            workspace_authority=self.child.workspace_authority, control_auth=self.child.control_auth)
        for value in (self.fixture.base, external_child, self.fixture.installation()):
            self.assertNotIn(HOST_SETTING, self.fixture.graph(value).node(value.cpk_node_id).non_secret_environment())

        for value in (self.child, self.fixture.base):
            product = value.cpk_product.product
            contract = product.runtime_contract
            conflicting = replace(contract, public_environment=(*contract.public_environment,
                PublicStaticEnvironmentBinding(HOST_SETTING, "other.example.test")))
            selected = self.fixture.codec.encode_document(replace(product, runtime_contract=conflicting))
            with self.assertRaises(ValueError):
                self.fixture.graph(replace(value, cpk_product=selected))

    def product_with_socket_deliveries(self, installation, *deliveries):
        product = installation.cpk_product.product
        contract = product.runtime_contract
        sockets = contract.sockets
        requirements = tuple(
            replace(socket, secret_deliveries=(*socket.secret_deliveries, *deliveries))
            if socket.name == "workplace-store" else socket for socket in sockets.requirements)
        contract = replace(contract, sockets=replace(sockets, requirements=requirements))
        return self.fixture.codec.encode_document(replace(product, runtime_contract=contract))

    def test_selected_product_refuses_socket_deliveries_to_reserved_host(self):
        reference = SecretReference("secret://fixture/socket-input")
        intent = SecretUseIntent.APPLICATION_CONTROL_TOKEN
        deliveries = (SecretEnvironmentDelivery(HOST_SETTING, reference, intent),
            SecretReferenceEnvironmentDelivery(HOST_SETTING, reference),
            SecretFileDelivery("/run/secrets/socket-input", reference, intent,
                path_binding=SecretFilePathBinding(HOST_SETTING)))
        for label, installation in (("bound", self.child), ("unbound", self.fixture.base)):
            for delivery in deliveries:
                with self.subTest(installation=label, delivery=type(delivery).__name__):
                    product = self.product_with_socket_deliveries(installation, delivery)
                    with self.assertRaisesRegex(ValueError, "^installation child MCP API hostname is reserved$"):
                        replace(installation, cpk_product=product)

    def test_ordinary_socket_deliveries_survive_child_installation(self):
        reference = SecretReference("secret://fixture/socket-input")
        intent = SecretUseIntent.APPLICATION_CONTROL_TOKEN
        deliveries = (SecretEnvironmentDelivery("SOCKET_INPUT", reference, intent),
            SecretReferenceEnvironmentDelivery("SOCKET_INPUT_REF", reference),
            SecretFileDelivery("/run/secrets/socket-input", reference, intent,
                path_binding=SecretFilePathBinding("SOCKET_INPUT_FILE")),
            SecretFileDelivery("/run/secrets/socket-file-only", reference, intent))
        for label, installation in (("bound", self.child), ("unbound", self.fixture.base)):
            with self.subTest(installation=label):
                product = self.product_with_socket_deliveries(installation, *deliveries)
                graph = self.fixture.graph(replace(installation, cpk_product=product))
                self.assertTrue(set(deliveries).issubset(graph.node(installation.cpk_node_id).secret_deliveries))

    def process_environment(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = Path(directory.name) / "policy.json"
        operator = {"subject_id": "child-reader", "kind": "operator"}
        identity = {"issuer": "urn:control-plane-kit:static-development", **operator}
        policy.write_text(json.dumps({"schema": "cpk-server.workspace-authority.v1",
            "installation_id": self.child.installation_id, "administrators": [identity],
            "known_identities": [identity], "capabilities": []}), encoding="utf-8")
        return {**self.node.non_secret_environment(),
            "CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE": str(policy),
            "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON": json.dumps([
                {**operator, "credential": "fixture-reader", "workspace_grants": {}}])}

    def test_configured_owner_rejects_missing_or_crossed_verifier_before_startup(self):
        env = self.process_environment()
        self.assertEqual(env["CPK_WORKSPACE_AUTHORITY"], "configured-owner-v1")
        key = "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"
        entries = json.loads(env[key])
        crossed = [{**entries[0], "subject_id": "different-owner"}]
        granted = [{**entries[0], "workspace_grants": {"other-workspace": ["instance:workspace:read"]}}]
        for label, document in (("missing", None), ("invalid", "{"), ("crossed", json.dumps(crossed)),
                                ("static grant", json.dumps(granted))):
            values = env.copy()
            if document is None:
                del values[key]
            else:
                values[key] = document
            with self.subTest(label=label), self.assertRaises(self.server.BootstrapConfigurationError):
                self.server.CpkServerBootstrapConfiguration.from_environment(values)

    def test_process_rejects_invalid_public_host_configuration(self):
        environment = self.process_environment()
        for invalid in ("", "*.example.test", "https://api.example.test", "api.example.test:443",
                        "api.example.test,other.example.test", "127.0.0.1", "cpk-source", "api.example.test."):
            with self.subTest(value=invalid), self.assertRaises(self.server.BootstrapConfigurationError):
                self.server.CpkServerBootstrapConfiguration.from_environment({**environment, HOST_SETTING: invalid})

    async def test_existing_named_installation_keeps_loopback_transport(self):
        value = self.fixture.installation()
        node = self.fixture.graph(value).node(value.cpk_node_id)
        config = self.server.CpkServerBootstrapConfiguration.from_environment({
            **node.non_secret_environment(), "CPK_CONTROL_AUTH_STATIC_CREDENTIAL": "fixture-reader"})
        services = {role: RecordingService(role.value) for role in ControlPlaneServiceRole}
        with patch.object(self.server, "_operations_application", return_value=CpkServerOperationsApplication(services)):
            app = self.server.create_app(config, self.server._credential_verifier(config), control=self.fixture.receiver(node))
        async with app.router.lifespan_context(app), httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), headers={"Authorization": "Bearer fixture-reader",
                "Accept": "application/json, text/event-stream"}) as http:
            local = await http.post("http://localhost:8080/mcp", json=INITIALIZE)
            self.assertEqual(local.status_code, 200)
            public = await http.post("https://" + value.ingress.hostname + "/mcp", json=INITIALIZE)
            self.assertEqual(public.status_code, 421)

    async def test_native_discovery_and_workspace_denial_at_composed_api(self):
        config = self.server.CpkServerBootstrapConfiguration.from_environment(self.process_environment())
        unit = MagicMock()
        stores = unit.__enter__.return_value.stores
        def permission(installation_id, workspace_id, identity):
            if workspace_id == "child-workspace":
                return WorkspacePermissionRecord(installation_id, workspace_id, identity,
                    (PolicyScope.INSTANCE_WORKSPACE_READ,), 1)
            return None
        stores.workspace_permissions.get.side_effect = permission
        stores.workspaces.get.return_value = WorkspaceRecord("child-workspace", "Child")
        services = {role: RecordingService(role.value) for role in ControlPlaneServiceRole}
        services[ControlPlaneServiceRole.READS] = CpkServerReadService(lambda: unit)
        application = CpkServerOperationsApplication(services, authority_mode="dynamic",
            workspace_context_resolver=WorkspaceContextResolver(lambda: unit,
                installation_id=self.child.installation_id))
        with patch.object(self.server, "_operations_application", return_value=application):
            app = self.server.create_app(config, self.server._credential_verifier(config),
                control=self.fixture.receiver(self.node))
        endpoint = "https://" + self.hostname
        async with app.router.lifespan_context(app), httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=endpoint,
            headers={"Accept": "application/json, text/event-stream"}) as http:
            denied = await http.post("/mcp", json=INITIALIZE)
            self.assertEqual(denied.status_code, 401)
            http.headers["Authorization"] = "Bearer fixture-reader"
            for mode in ("auto", "legacy"):
                with self.subTest(mode=mode):
                    async with Client(streamable_http_client(endpoint + "/mcp", http_client=http), mode=mode) as client:
                        self.assertIn("get_workspace", {tool.name for tool in (await client.list_tools()).tools})
                        allowed = await client.call_tool("get_workspace", {"workspace_id": "child-workspace"})
                        self.assertFalse(allowed.is_error)
                        self.assertEqual(allowed.structured_content["workspace"]["workspace_id"], "child-workspace")
                        stores.workspaces.get.reset_mock()
                        result = await client.call_tool("get_workspace", {"workspace_id": "ungranted-workspace"})
                        self.assertTrue(result.is_error)
                        self.assertEqual(result.structured_content["error"]["status"], 403)
                        stores.workspaces.get.assert_not_called()

            website = self.child.website.ingress.hostname
            management = self.child.management.management_ingress.hostname
            for host in (website, management, "other.example.test", self.hostname + ":443", "localhost:0"):
                with self.subTest(host=host):
                    response = await http.post("/mcp", json=INITIALIZE,
                        headers={"Host": host, "X-Forwarded-Host": self.hostname})
                    self.assertEqual(response.status_code, 421)
            for origin in (endpoint, "https://" + website, "https://" + management, "null", ""):
                with self.subTest(origin=origin):
                    response = await http.post("/mcp", json=INITIALIZE, headers={"Origin": origin})
                    self.assertEqual(response.status_code, 403)
            for name, value, status in (("Host", self.hostname, 421), ("Origin", "http://localhost:8080", 403)):
                response = await http.post("/mcp", json=INITIALIZE, headers=[(name, value), (name, value)])
                self.assertEqual(response.status_code, status)
            local = await http.post("http://127.0.0.1:8080/mcp", json=INITIALIZE,
                headers={"Origin": "http://127.0.0.1:8080"})
            self.assertEqual(local.status_code, 200)
