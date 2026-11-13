"""Ordinary released MCP client against the actual authenticated ASGI host."""
import asyncio
from dataclasses import replace
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import traceback
import unittest
from unittest.mock import MagicMock, Mock

import httpx2
import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations.cpk_server import CpkServerReadService

import test_http_host as host_fixture
from test_http_mcp_boundaries import _principal


class StandardMcpFixture:
    async def asyncSetUp(self):
        self.host = host_fixture.CpkHttpHostTests("test_every_operator_contract_reaches_unchanged_auth_boundary")
        self.host.mcp_profile = getattr(self, "mcp_profile", "standard")
        self.host.setUp()
        self.addCleanup(self.host.tearDown)
        self.app = self.host.app
        started, stopped = asyncio.Event(), asyncio.Event()
        async def lifespan():
            async with self.app.router.lifespan_context(self.app):
                started.set()
                await stopped.wait()
        lifecycle = asyncio.create_task(lifespan())
        await started.wait()
        async def close_lifespan():
            stopped.set()
            await lifecycle
        self.addAsyncCleanup(close_lifespan)
        self.http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),
            base_url="http://127.0.0.1:8080", headers={"Authorization": "Bearer valid-token"})
        self.addAsyncCleanup(self.http.aclose)

    def client(self, mode="auto", http=None):
        return Client(streamable_http_client("http://127.0.0.1:8080/mcp", http_client=http or self.http), mode=mode)


class StandardMcpLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_host_restarts_with_authenticated_sdk_reads_in_both_eras(self):
        host = host_fixture.CpkHttpHostTests("test_every_operator_contract_reaches_unchanged_auth_boundary")
        host.mcp_profile = getattr(self, "mcp_profile", "standard")
        host.setUp()
        self.addCleanup(host.tearDown)
        app = host.app
        for cycle in range(2):
            with self.subTest(cycle=cycle):
                async with app.router.lifespan_context(app):
                    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),
                            base_url="http://127.0.0.1:8080",
                            headers={"Authorization": "Bearer valid-token"}) as http:
                        before = sum(len(service.requests) for service in host.services.values())
                        denied = await http.post("/mcp", content=b"{}",
                            headers={"Authorization": "Bearer rejected"})
                        self.assertEqual(denied.status_code, 401)
                        self.assertEqual(sum(len(service.requests) for service in host.services.values()), before)
                        expected = await http.get("/workspaces/workspace-a")
                        self.assertEqual(expected.status_code, 200)
                        for mode in ("auto", "legacy"):
                            async with Client(streamable_http_client(
                                    "http://127.0.0.1:8080/mcp", http_client=http), mode=mode) as client:
                                tools = {tool.name for tool in (await client.list_tools()).tools}
                                self.assertIn("get_workspace", tools)
                                result = await client.call_tool("get_workspace", {"workspace_id": "workspace-a"})
                                self.assertFalse(result.is_error)
                                self.assertEqual(result.structured_content["route_id"], expected.json()["route_id"])
                                self.assertEqual(result.structured_content["principal"], expected.json()["principal"])


class StandardMcpTests(StandardMcpFixture, unittest.IsolatedAsyncioTestCase):
    async def test_released_client_discovers_and_reads_in_both_protocol_eras(self):
        for mode, protocol in (("auto", "2026-07-28"), ("legacy", "2025-11-25")):
            with self.subTest(mode=mode):
                async with self.client(mode) as client:
                    self.assertEqual(client.protocol_version, protocol)
                    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                    for name, arguments, path in (
                        ("get_workspace", {"workspace_id": "workspace-a"}, "/workspaces/workspace-a"),
                        ("get_desired_graph", {"workspace_id": "workspace-a"}, "/workspaces/workspace-a/graphs/desired"),
                        ("get_desired_topology_draft_revision", {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 7},
                         "/workspaces/workspace-a/desired-topology-drafts/draft-a/revisions/7"),
                        ("list_desired_topology_draft_revision_attempts", {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 7},
                         "/workspaces/workspace-a/desired-topology-drafts/draft-a/revisions/7/attempts"),
                    ):
                        self.assertIn(name, tools)
                        tool = tools[name]
                        self.assertTrue(tool.annotations.read_only_hint)
                        self.assertIn("workspace_id", tool.input_schema["required"])
                        result = await client.call_tool(name, arguments)
                        self.assertFalse(result.is_error)
                        http = await self.http.get(path)
                        self.assertEqual(http.status_code, 200)
                        # Recording services expose wire layout; compare the owner route,
                        # identity and argument values, not transport-specific layout.
                        expected = http.json()
                        actual = result.structured_content
                        self.assertEqual(actual["route_id"], expected["route_id"])
                        self.assertEqual(actual["principal"], expected["principal"])
                        combined = {**expected["path_parameters"], **expected["payload"]}
                        self.assertEqual({key: str(value) for key, value in actual["payload"].items()},
                                         {key: str(value) for key, value in combined.items()})
                    self.assertTrue(all(tool.annotations.read_only_hint for name, tool in tools.items() if name != "prepare_deployment"))
                    self.assertEqual({name for name, tool in tools.items() if not tool.annotations.read_only_hint}, {"prepare_deployment"})
                    self.assertNotIn("provision_secret_material", tools)
                    self.assertIn("redacted", tools["get_desired_graph"].description.lower())

    async def test_authentication_and_strict_json_fail_before_dispatch(self):
        before = sum(len(service.requests) for service in self.host.services.values())
        for body, token, expected in (
            (b"invalid JSON", "rejected", 401),
            (b'{"jsonrpc":"2.0","id":1,"id":2}', "valid-token", 400),
            (b'{"value":NaN}', "valid-token", 400),
            (b'{"value":1e999}', "valid-token", 400),
            (b'{"value":' + b'[' * 65 + b'0' + b']' * 65 + b'}', "valid-token", 400),
            (b"x" * 1_048_577, "valid-token", 413),
        ):
            response = await self.http.post("/mcp", content=body, headers={
                "Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json"})
            self.assertEqual(response.status_code, expected)
            self.assertNotIn(token, response.text)
        self.assertEqual(sum(len(service.requests) for service in self.host.services.values()), before)

    async def test_connection_security_and_exact_path(self):
        for path in ("/mcp/", "/mcp/unknown"):
            response = await self.http.post(path, json={})
            self.assertEqual(response.status_code, 404)
        for header, value, code in (("Origin", "https://foreign.invalid", 403),
                                    ("Host", "foreign.invalid", 421)):
            response = await self.http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers={header: value, "Accept": "application/json, text/event-stream"})
            self.assertEqual(response.status_code, code)

    async def test_route_bounds_unknown_confidential_calls_and_owner_denial(self):
        reads = self.host.services[ControlPlaneServiceRole.READS]
        async with self.client() as client:
            for name, arguments, status in (
                ("get_workspace", {"workspace_id": "x" * 65537}, 413),
                ("get_workspace", {"workspace_id": "workspace-a", "unknown": True}, 400),
                ("provision_secret_material", {}, 404),
                ("command.secret-material.provision", {}, 404),
            ):
                result = await client.call_tool(name, arguments)
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content["error"]["status"], status)
            self.assertEqual(reads.requests, [])
            reads.handle = lambda request: {"value": "x" * 1_048_577}
            result = await client.call_tool("get_workspace", {"workspace_id": "workspace-a"})
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["error"]["status"], 503)
            touched = []
            def unopened():
                touched.append(True)
                raise AssertionError("denied read reached store")
            reads.handle = CpkServerReadService(unopened).handle
            result = await client.call_tool("get_workspace", {"workspace_id": "workspace-a"})
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["error"]["status"], 403)
            self.assertEqual(touched, [])

    async def test_principals_are_request_local_and_changed_credentials_are_rechecked(self):
        principals = {name: replace(_principal(), identity=replace(_principal().identity, subject_id=name))
                      for name in ("first", "second")}
        def authenticate(credential):
            return principals[credential.decode()]
        self.host.verifier.authenticate = authenticate
        reads = self.host.services[ControlPlaneServiceRole.READS]
        async def handle_async(request):
            await asyncio.sleep(0)
            return reads.handle(request)
        reads.handle_async = handle_async
        async def read(name):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),
                    headers={"Authorization": "Bearer " + name}) as http:
                async with self.client(http=http) as client:
                    result = await client.call_tool("get_workspace", {"workspace_id": "workspace-a"})
                    return result.structured_content["principal"]
        results = await asyncio.gather(read("first"), read("second"))
        self.assertEqual(results, json.loads(json.dumps([principals[name].descriptor() for name in ("first", "second")])))
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),
                headers={"Authorization": "Bearer first"}) as http:
            async with self.client(http=http) as client:
                count = len(reads.requests)
                principals.pop("first")
                with self.assertRaises(Exception):
                    await client.call_tool("get_workspace", {"workspace_id": "workspace-a"})
                self.assertEqual(len(reads.requests), count)

    async def test_malformed_sdk_frames_and_arguments_never_reflect_private_canary(self):
        canary = "private-input-canary-not-for-diagnostics"
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logging.getLogger("mcp").addHandler(handler)
        self.addCleanup(logging.getLogger("mcp").removeHandler, handler)
        before = sum(len(service.requests) for service in self.host.services.values())
        for version in ("2025-11-25", "2026-07-28"):
            for frame in (
                {"jsonrpc": canary, "id": 1, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 1, "method": {"private": canary}},
                {"jsonrpc": "2.0", "id": {"private": canary}, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_workspace", "arguments": canary}},
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_workspace",
                    "arguments": {"workspace_id": "workspace-a", "unknown": canary}}},
            ):
                response = await self.http.post("/mcp", json=frame, headers={
                    "MCP-Protocol-Version": version, "Accept": "application/json, text/event-stream",
                    "Mcp-Method": frame["method"] if isinstance(frame["method"], str) else "tools/call",
                    "Mcp-Name": "get_workspace"})
                self.assertNotIn(canary, response.text)
                self.assertLess(len(response.content), 8192)
                # The official union can classify an invalid-id frame as a
                # notification. Its accepted response must remain empty and
                # produce no application dispatch; we do not redefine framing.
                if isinstance(frame.get("id"), dict):
                    # SDK legacy uses its union; modern uses id-presence and
                    # JSONRPCRequest.model_validate (modern transport:419-427).
                    expected = 202 if version == "2025-11-25" else 400
                    self.assertEqual(response.status_code, expected, version)
                    if expected == 202:
                        self.assertEqual(response.content, b"")
                elif frame["jsonrpc"] != "2.0" or not isinstance(frame["method"], str):
                    self.assertEqual(response.status_code, 400)
                else:
                    self.assertIn(response.status_code, (200, 400))
        self.assertNotIn(canary, stream.getvalue())
        self.assertEqual(sum(len(service.requests) for service in self.host.services.values()), before)

    async def test_actual_owner_reads_preserve_revision_identity_and_redacted_http_parity(self):
        from control_plane_kit_operations.records import GraphVersionRecord, WorkspaceRecord
        from control_plane_kit_operations.desired_topology_drafts import DesiredTopologyDraftRevisionRecord
        from control_plane_kit_operations.read_pages import ReadPage
        canary = "synthetic-private-graph-value"
        instant = "2026-11-12T00:00:00Z"
        graph = {"name": "saved", "runtimes": {}, "nodes": {}, "edges": {}, "public_ingresses": []}
        saved = GraphVersionRecord("graph-saved", "workspace-a", 7, graph, "fixture", instant)
        # Immutable store-return fixtures only; actual owner projections perform
        # redaction, catalogue validation and page construction. No store/state
        # machine, persistence or mutation behavior is implemented in this test.
        desired = GraphVersionRecord("graph-desired", "workspace-a", 8,
            {**graph, "nodes": {"fixture": {"environment": {"SYNTHETIC": canary}}}}, "fixture", instant)
        workspace = WorkspaceRecord("workspace-a", "Fixture", desired_graph_id=desired.graph_id,
            desired_realized_projection_id="projection-desired", desired_graph_revision=1)
        stores = Mock()
        stores.workspaces.get.return_value = workspace
        stores.graphs.get.side_effect = {saved.graph_id: saved, desired.graph_id: desired}.__getitem__
        stores.desired_topology_drafts.revision.return_value = DesiredTopologyDraftRevisionRecord(
            "workspace-a", "draft-a", 7, saved.graph_id, "fixture", instant)
        stores.revision_history.presence.return_value = {"preparations": False, "attempts": False}
        stores.revision_history.page.side_effect = lambda request: ReadPage.from_candidates(request, ())
        unit = MagicMock()
        unit.__enter__.return_value = unit
        unit.stores = stores
        service = CpkServerReadService(lambda: unit)
        self.host.services[ControlPlaneServiceRole.READS].handle = service.handle
        principal = replace(_principal(), workspace_grants=(WorkspaceGrant(
            "workspace-a", (PolicyScope.INSTANCE_WORKSPACE_READ,)),))
        self.host.verifier.authenticate = lambda credential: principal
        async with self.client() as client:
            for name, arguments, path in (
                ("get_workspace", {"workspace_id": "workspace-a"}, "/workspaces/workspace-a"),
                ("get_desired_graph", {"workspace_id": "workspace-a"}, "/workspaces/workspace-a/graphs/desired"),
                ("get_desired_topology_draft_revision", {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 7},
                    "/workspaces/workspace-a/desired-topology-drafts/draft-a/revisions/7"),
                ("list_desired_topology_draft_revision_attempts", {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 7},
                    "/workspaces/workspace-a/desired-topology-drafts/draft-a/revisions/7/attempts"),
            ):
                result = await client.call_tool(name, arguments)
                self.assertFalse(result.is_error, result.structured_content)
                http = await self.http.get(path)
                self.assertEqual(http.status_code, 200)
                self.assertEqual(result.structured_content, http.json())
                self.assertNotIn(canary, json.dumps(result.structured_content))
                if name == "get_desired_topology_draft_revision":
                    self.assertEqual((result.structured_content["draft_id"], result.structured_content["revision"],
                                      result.structured_content["graph_id"]), ("draft-a", 7, saved.graph_id))

    def test_legacy_endpoint_selection_is_explicit_and_never_falls_back(self):
        from scripts.cpk_server_public_graph_convergence import McpTransport, PublicConvergenceError
        paths = []
        def received(request):
            paths.append(request.url.path)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": "fixture", "result": {"fixture": True}})
        with httpx.Client(base_url="http://fixture.invalid", transport=httpx.MockTransport(received)) as http:
            for endpoint in ("/mcp/legacy", "/mcp"):
                result = McpTransport(http, endpoint=endpoint).invoke("read.workspace", {"workspace_id": "workspace-a"},
                    authorization="Bearer synthetic-fixture")
                self.assertEqual(result, {"fixture": True})
            self.assertEqual(paths, ["/mcp/legacy", "/mcp"])
            with self.assertRaises(PublicConvergenceError):
                McpTransport(http, endpoint="/unknown")
            self.assertEqual(len(paths), 2)
        root = Path(__file__).resolve().parents[3]
        for name in ("cpk_server_image_smoke.sh", "cpk_server_hosted_activity_smoke.sh",
                     "cpk_server_public_graph_convergence_smoke.sh"):
            result = subprocess.run(["sh", str(root / "scripts" / name)], cwd=root,
                env={**os.environ, "CPK_LEGACY_MCP_PATH": "/unknown"}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr.strip(), "unsupported legacy MCP endpoint")

    async def test_rejection_send_failure_preserves_identity_without_private_exception_context(self):
        canary = "synthetic-private-input-not-for-tracebacks"
        for body, credential, status in (
            (json.dumps({"jsonrpc": canary, "id": 1, "method": "tools/list"}).encode(), b"valid-token", 400),
            (b"{}", canary.encode(), 401),
            (canary.encode() + b"x" * 1_048_577, b"valid-token", 413),
        ):
            with self.subTest(status=status):
                sent = []
                failure = OSError("synthetic client disconnect")
                async def receive():
                    return {"type": "http.request", "body": body, "more_body": False}
                async def send(message):
                    sent.append(message)
                    raise failure
                scope = {"type": "http", "http_version": "1.1", "scheme": "http", "method": "POST",
                    "path": "/mcp", "raw_path": b"/mcp", "query_string": b"",
                    "server": ("127.0.0.1", 8080), "client": ("127.0.0.1", 12345),
                    "headers": [(b"host", b"127.0.0.1:8080"), (b"authorization", b"Bearer " + credential),
                                (b"content-type", b"application/json")], "state": {}}
                with self.assertRaises(OSError) as caught:
                    await self.app(scope, receive, send)
                self.assertIs(caught.exception, failure)
                self.assertIsNone(caught.exception.__context__)
                self.assertIsNone(caught.exception.__cause__)
                self.assertNotIn(canary, "".join(traceback.format_exception(caught.exception)))
                self.assertEqual(sent[0]["status"], status)
        self.host.assert_no_service_work()
