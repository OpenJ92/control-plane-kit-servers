"""Public source-live transport identities and bounded failure behavior."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_hosted_gateway_delegation_bootstrap import _controller_module
from test_ephemeral_source_live_lifecycle import _controller_module as _source_controller


@contextmanager
def responding_server(*, status=200, body=None, redirect=False):
    observed = []
    encoded = json.dumps({"result": {"accepted": True}} if body is None else body).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            observed.append((self.path, self.headers.get("Authorization"), request))
            self.send_response(302 if redirect else status)
            if redirect:
                self.send_header("Location", "/redirected")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", observed
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


class SourceLivePublicTransportTests(unittest.TestCase):
    def test_isolation_reaches_foreign_checks_with_owner_graph_pointer_shape(self):
        from control_plane_kit_operations.read_services.workspace_graph import GraphPointerReadModel
        from control_plane_kit_servers_cpk_server.client.transport import ClientAuthorizationError

        pointer = GraphPointerReadModel("current", True, graph_id="graph-a",
            authored_graph_id="graph-a", realized_projection_id="projection-a").descriptor()
        observed = []

        class Transport:
            def __init__(self, profile, *, surface):
                self.surface = surface

            def call(self, route_id, *, path_parameters, payload, credential_role):
                observed.append((self.surface, route_id, dict(path_parameters), credential_role))
                if path_parameters["workspace_id"] == "workspace-b":
                    raise ClientAuthorizationError()
                if route_id == "read.workspace":
                    return {"workspace": {"workspace_id": "workspace-a"}}
                return pointer

        fixture = SimpleNamespace(profiles={"workspace-a": object()})
        foreign_result = SimpleNamespace(workspace_id="workspace-b", plan_id="plan-b", run_id="run-b")
        with _source_controller() as controller, patch.object(controller, "_EnrollmentTransport", Transport):
            controller._require_enrollment_workspace_isolation(fixture,
                {"workspace_id": "workspace-a"}, {"workspace_id": "workspace-b"}, foreign_result)
        for surface in ("http", "mcp"):
            self.assertEqual([row[1:] for row in observed if row[0] == surface], [
                ("read.workspace", {"workspace_id": "workspace-a"}, "operator"),
                ("read.current-graph", {"workspace_id": "workspace-a"}, "operator"),
                ("read.current-graph", {"workspace_id": "workspace-b"}, "operator"),
                ("read.plan-detail", {"workspace_id": "workspace-b", "plan_id": "plan-b"}, "operator"),
                ("read.run-events", {"workspace_id": "workspace-b", "run_id": "run-b"}, "operator"),
            ])

    def test_scenario_does_not_approve_an_unexpected_destructive_plan(self):
        from control_plane_kit_servers_cpk_server.client.workflow import ClientResult

        client = Mock()
        client.plan.return_value = ClientResult("planned", "operation-a", "workspace-a",
            plan_id="plan-a", destructive=True)
        fixture = SimpleNamespace(profiles={"workspace-a": object()})
        enrolled = {"workspace_id": "workspace-a", "ordinary": object()}
        with _source_controller() as controller, patch(
                "control_plane_kit_servers_cpk_server.client.TopologyClient", return_value=client):
            from scripts.cpk_server_source_live_report import SourceLiveInvariantError
            with self.assertRaises(SourceLiveInvariantError):
                controller._apply_enrollment_topology(fixture, enrolled, Path("selected.json"),
                    title="Create approved workload", destructive=False)
        client.apply.assert_not_called()
        client.status.assert_not_called()

    def test_scenario_stops_after_uncertain_application_without_retry(self):
        from control_plane_kit_servers_cpk_server.client.workflow import ClientResult

        client = Mock()
        client.plan.return_value = ClientResult("planned", "operation-a", "workspace-a",
            plan_id="plan-a", destructive=False)
        client.apply.return_value = ClientResult("attention-required", "operation-a", "workspace-a",
            plan_id="plan-a", run_id="run-a", execution="uncertain")
        fixture = SimpleNamespace(profiles={"workspace-a": object()})
        enrolled = {"workspace_id": "workspace-a", "ordinary": object()}
        with _source_controller() as controller, patch(
                "control_plane_kit_servers_cpk_server.client.TopologyClient", return_value=client):
            from scripts.cpk_server_source_live_report import SourceLiveInvariantError
            with self.assertRaises(SourceLiveInvariantError):
                controller._apply_enrollment_topology(fixture, enrolled, Path("selected.json"),
                    title="Create approved workload", destructive=False)
        self.assertEqual(client.plan.call_count, 1)
        client.apply.assert_called_once_with("operation-a", execute_plan="plan-a", approve_plan="plan-a")
        client.status.assert_not_called()

    def test_scenario_requires_public_confirmation_of_the_exact_applied_run(self):
        from control_plane_kit_servers_cpk_server.client.workflow import ClientResult

        client = Mock()
        client.plan.return_value = ClientResult("planned", "operation-a", "workspace-a",
            plan_id="plan-a", destructive=True)
        applied = ClientResult("converged", "operation-a", "workspace-a", plan_id="plan-a",
            run_id="run-a", execution="succeeded", advancement="advanced")
        client.apply.return_value = applied
        fixture = SimpleNamespace(profiles={"workspace-a": object()})
        enrolled = {"workspace_id": "workspace-a", "ordinary": object()}
        for run_id in ("run-foreign", "run-a"):
            with self.subTest(public_run=run_id), _source_controller() as controller, patch(
                    "control_plane_kit_servers_cpk_server.client.TopologyClient", return_value=client):
                from scripts.cpk_server_source_live_report import SourceLiveInvariantError
                client.status.return_value = ClientResult("converged", "operation-a", "workspace-a",
                    plan_id="plan-a", run_id=run_id, execution="succeeded", advancement="advanced")
                if run_id == "run-foreign":
                    with self.assertRaises(SourceLiveInvariantError):
                        controller._apply_enrollment_topology(fixture, enrolled, Path("empty.json"),
                            title="Remove approved workload", destructive=True)
                else:
                    self.assertIs(controller._apply_enrollment_topology(fixture, enrolled, Path("empty.json"),
                        title="Remove approved workload", destructive=True), applied)
                client.apply.assert_called_with("operation-a", execute_plan="plan-a",
                    approve_destructive_plan="plan-a")
                client.status.assert_called_with("operation-a")

    def test_reads_and_commands_use_the_explicit_identity(self):
        with _controller_module() as controller, responding_server() as (endpoint, observed):
            with patch.object(controller, "AUTHORIZATION", "Bearer unrelated-default"):
                self.assertEqual(controller._mcp_read(endpoint, "read.current-graph",
                    {"workspace_id": "workspace-b"}, authorization="Bearer reader-b"), {"accepted": True})
                self.assertEqual(controller._mcp_tool(endpoint, "command.workspace-permission.revoke",
                    {"workspace_id": "workspace-b"}, authorization="Bearer administrator-b"), {"accepted": True})
        self.assertEqual([item[1] for item in observed], ["Bearer reader-b", "Bearer administrator-b"])
        self.assertEqual([item[2]["method"] for item in observed], ["resources/read", "tools/call"])
        self.assertEqual([item[2]["params"]["arguments"] for item in observed],
            [{"workspace_id": "workspace-b"}] * 2)

    def test_http_denial_retains_only_status_without_response_or_exception_context(self):
        with _controller_module() as controller, responding_server(status=403,
                body={"private": "foreign-provider-secret"}) as (endpoint, observed):
            with self.assertRaises(controller.SourceLiveHttpError) as raised:
                controller._mcp_read(endpoint, "read.current-graph", {}, authorization="Bearer denied-reader")
            self.assertEqual(raised.exception.status, 403)
            self.assertNotIn("foreign-provider-secret", str(raised.exception))
            self.assertNotIn("denied-reader", str(raised.exception))
            self.assertIsNone(raised.exception.__context__)
        self.assertEqual(len(observed), 1)

    def test_mcp_error_and_invalid_result_do_not_echo_provider_payloads(self):
        for body in ({"error": {"message": "foreign-provider-secret"}},
                     {"result": "foreign-provider-secret"}):
            with self.subTest(body_kind=next(iter(body))):
                with _controller_module() as controller, responding_server(body=body) as (endpoint, _):
                    with self.assertRaises(RuntimeError) as raised:
                        controller._mcp_read(endpoint, "read.current-graph", {}, authorization="Bearer reader")
                    self.assertNotIn("foreign-provider-secret", str(raised.exception))
                    self.assertIsNone(raised.exception.__context__)

    def test_redirect_does_not_forward_the_authenticated_request(self):
        with _controller_module() as controller, responding_server(redirect=True) as (endpoint, observed):
            with self.assertRaises(controller.SourceLiveHttpError) as raised:
                controller._mcp_tool(endpoint, "command.workspace-administration.create", {},
                    authorization="Bearer administrator")
            self.assertEqual(raised.exception.status, 302)
        self.assertEqual([item[0] for item in observed], ["/mcp"])

    def test_enrollment_mcp_adapter_uses_catalogue_routes_and_profile_roles(self):
        from control_plane_kit_servers_cpk_server.client.profile import ClientProfile

        with TemporaryDirectory() as directory, responding_server() as (endpoint, observed):
            root = Path(directory)
            credentials = {}
            for role in ("operator", "approver", "worker"):
                credentials[role] = root / role
                credentials[role].write_text("synthetic-" + role, encoding="ascii")
                credentials[role].chmod(0o600)
            profile = ClientProfile(endpoint, "workspace-b", credentials, root / "state")
            with _source_controller() as controller:
                transport = controller._EnrollmentTransport(profile, surface="mcp")
                transport.call("read.current-graph", path_parameters={"workspace_id": "workspace-b"},
                    payload={}, credential_role="operator")
                transport.call("command.workspace-administration.create", path_parameters={},
                    payload={"workspace_id": "workspace-b", "name": "B", "idempotency_key": "create-b"},
                    credential_role="approver")
        self.assertEqual([item[1] for item in observed], ["Bearer synthetic-operator", "Bearer synthetic-approver"])
        self.assertEqual([item[2]["method"] for item in observed], ["resources/read", "tools/call"])
        self.assertEqual([item[2]["params"]["name"] for item in observed],
            ["get_current_graph", "create_workspace_as_administrator"])
        self.assertEqual(observed[0][2]["params"]["arguments"], {"workspace_id": "workspace-b"})

    def test_enrollment_adapter_preserves_authorization_refusal_without_raw_context(self):
        from control_plane_kit_servers_cpk_server.client.profile import ClientProfile
        from control_plane_kit_servers_cpk_server.client.transport import ClientAuthorizationError

        with TemporaryDirectory() as directory, responding_server(status=403,
                body={"private": "foreign-grant"}) as (endpoint, _):
            root = Path(directory)
            token = root / "credential"
            token.write_text("synthetic-denied", encoding="ascii")
            token.chmod(0o600)
            profile = ClientProfile(endpoint, "workspace-b",
                {role: token for role in ("operator", "approver", "worker")}, root / "state")
            with _source_controller() as controller:
                transport = controller._EnrollmentTransport(profile, surface="mcp")
                with self.assertRaises(ClientAuthorizationError) as raised:
                    transport.call("read.current-graph", path_parameters={"workspace_id": "workspace-b"},
                        payload={}, credential_role="operator")
                self.assertIsNone(raised.exception.__context__)
                self.assertNotIn("foreign-grant", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
