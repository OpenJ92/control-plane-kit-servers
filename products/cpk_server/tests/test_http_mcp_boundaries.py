from pathlib import Path
import sys
import unittest

from control_plane_kit_core.operations import ControlPlaneServiceRole


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"


class RecordingService:
    def __init__(self, name: str) -> None:
        self.name = name
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        return {
            "service": self.name,
            "route_id": request.route_id,
            "surface": request.surface,
            "path_parameters": request.path_parameters,
            "payload": request.payload,
        }


class CpkServerHttpMcpBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(PRODUCT_SRC))

    def tearDown(self) -> None:
        sys.path.remove(str(PRODUCT_SRC))
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith(
                "control_plane_kit_servers_cpk_server."
            ):
                sys.modules.pop(name, None)

    def _application(self):
        from control_plane_kit_servers_cpk_server import (
            CpkServerApplicationBoundary,
            CpkServerProcessConfiguration,
            create_cpk_server_composition,
        )

        composition = create_cpk_server_composition(
            CpkServerProcessConfiguration.execution_capable(token_configured=True)
        )
        services = {
            role: RecordingService(role.value)
            for role in ControlPlaneServiceRole
        }
        return composition, services, CpkServerApplicationBoundary(services)


    def test_product_local_law_cards_assign_814_owned_laws(self) -> None:
        import json

        cards = json.loads(
            (ROOT / "products" / "cpk_server" / "law-cards" / "extract-f-814.json")
            .read_text(encoding="utf-8")
        )

        self.assertEqual(cards["schema"], "cpk-server.extract-f-law-cards")
        self.assertEqual(cards["issue"], "#814")
        self.assertEqual(
            [card["law"] for card in cards["law_cards"]],
            [
                "behavior.configured-token-protects-control-routes",
                "behavior.control-routes-can-be-called-without-token-when-unconfigured",
                "behavior.execution-auth-does-not-protect-ordinary-data-routes",
                "behavior.execution-mutation-body-is-bounded-before-application",
                "behavior.observers-route-mutates-state",
                "behavior.unknown-active-target-returns-bad-request",
            ],
        )
        self.assertTrue(
            all(card["owner"] == "control-plane-kit-servers/cpk_server" for card in cards["law_cards"])
        )

    def test_http_read_route_delegates_to_shared_reads_service(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)

        response = http.handle(
            method="GET",
            path="/workspaces/workspace-a/graphs/current",
            headers={"Authorization": "Bearer present"},
            body=b"",
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["service"], "reads")
        self.assertEqual(response.body["route_id"], "read.current-graph")
        self.assertEqual(response.body["surface"], "http")
        self.assertEqual(response.body["path_parameters"], {"workspace_id": "workspace-a"})
        self.assertEqual(len(services[ControlPlaneServiceRole.READS].requests), 1)

    def test_http_command_route_requires_auth_and_delegates_to_planning(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)

        rejected = http.handle(
            method="POST",
            path="/workspaces/workspace-a/plans",
            headers={},
            body=b'{"change":"blue-to-green"}',
        )
        accepted = http.handle(
            method="POST",
            path="/workspaces/workspace-a/plans",
            headers={"Authorization": "Bearer present"},
            body=b'{"change":"blue-to-green"}',
        )

        self.assertEqual(rejected.status, 401)
        self.assertNotIn("Bearer present", repr(rejected.body))
        self.assertEqual(accepted.status, 200)
        self.assertEqual(accepted.body["service"], "planning")
        self.assertEqual(accepted.body["payload"], {"change": "blue-to-green"})
        self.assertEqual(len(services[ControlPlaneServiceRole.PLANNING].requests), 1)

    def test_http_malformed_and_oversized_payloads_fail_before_services(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)

        malformed = http.handle(
            method="POST",
            path="/workspaces/workspace-a/plans",
            headers={"Authorization": "Bearer present"},
            body=b'{',
        )
        oversized = http.handle(
            method="POST",
            path="/workspaces/workspace-a/plans",
            headers={"Authorization": "Bearer present"},
            body=b'{"x":"' + (b"a" * 70000) + b'"}',
        )

        self.assertEqual(malformed.status, 400)
        self.assertEqual(oversized.status, 413)
        self.assertEqual(services[ControlPlaneServiceRole.PLANNING].requests, [])

    def test_mcp_tools_call_uses_same_application_boundary_as_http(self) -> None:
        from control_plane_kit_servers_cpk_server import (
            CpkServerHttpProcessBoundary,
            CpkServerMcpProcessBoundary,
        )

        composition, services, application = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)
        mcp = CpkServerMcpProcessBoundary(composition, application)

        self.assertIs(http.application, mcp.application)

        result = mcp.handle(
            headers={
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
                "Mcp-Method": "tools/call",
                "Authorization": "Bearer present",
            },
            message={
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {
                    "name": "command.deployment.plan",
                    "arguments": {"workspace_id": "workspace-a", "change": "green"},
                },
            },
        )

        self.assertEqual(result.status, 200)
        self.assertEqual(result.body["result"]["service"], "planning")
        self.assertEqual(result.body["result"]["surface"], "mcp")
        self.assertEqual(len(services[ControlPlaneServiceRole.PLANNING].requests), 1)

    def test_mcp_resources_read_uses_read_service_and_auth_failures_are_bounded(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerMcpProcessBoundary

        composition, services, application = self._application()
        mcp = CpkServerMcpProcessBoundary(composition, application)

        missing_auth = mcp.handle(
            headers={
                "Accept": "application/json",
                "MCP-Protocol-Version": "2025-06-18",
                "Mcp-Method": "resources/read",
            },
            message={
                "jsonrpc": "2.0",
                "id": "read-1",
                "method": "resources/read",
                "params": {"name": "read.current-graph", "arguments": {"workspace_id": "workspace-a"}},
            },
        )
        accepted = mcp.handle(
            headers={
                "Accept": "application/json",
                "MCP-Protocol-Version": "2025-06-18",
                "Mcp-Method": "resources/read",
                "Authorization": "Bearer present",
            },
            message={
                "jsonrpc": "2.0",
                "id": "read-1",
                "method": "resources/read",
                "params": {"name": "read.current-graph", "arguments": {"workspace_id": "workspace-a"}},
            },
        )

        self.assertEqual(missing_auth.status, 401)
        self.assertEqual(accepted.status, 200)
        self.assertEqual(accepted.body["result"]["service"], "reads")
        self.assertEqual(len(services[ControlPlaneServiceRole.READS].requests), 1)

    def test_unknown_http_and_mcp_operations_fail_closed(self) -> None:
        from control_plane_kit_servers_cpk_server import (
            CpkServerHttpProcessBoundary,
            CpkServerMcpProcessBoundary,
        )

        composition, services, application = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)
        mcp = CpkServerMcpProcessBoundary(composition, application)

        http_response = http.handle(
            method="GET",
            path="/workspaces/workspace-a/not-real",
            headers={"Authorization": "Bearer present"},
            body=b"",
        )
        mcp_response = mcp.handle(
            headers={
                "Accept": "application/json",
                "MCP-Protocol-Version": "2025-06-18",
                "Mcp-Method": "tools/call",
                "Authorization": "Bearer present",
            },
            message={
                "jsonrpc": "2.0",
                "id": "bad-1",
                "method": "tools/call",
                "params": {"name": "command.not-real", "arguments": {}},
            },
        )

        self.assertEqual(http_response.status, 404)
        self.assertEqual(mcp_response.status, 404)
        self.assertTrue(all(service.requests == [] for service in services.values()))


if __name__ == "__main__":
    unittest.main()
