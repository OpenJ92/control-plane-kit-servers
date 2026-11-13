"""Ordinary released MCP client against the actual authenticated ASGI host."""
import asyncio
from dataclasses import replace
import unittest

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_operations.cpk_server import CpkServerReadService

import test_http_host as host_fixture
from test_http_mcp_boundaries import _principal


class StandardMcpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.host = host_fixture.CpkHttpHostTests("test_every_operator_contract_reaches_unchanged_auth_boundary")
        self.host.setUp()
        self.addCleanup(self.host.tearDown)
        self.app = self.host.app
        self.lifecycle = self.app.router.lifespan_context(self.app)
        await self.lifecycle.__aenter__()
        self.addAsyncCleanup(self.lifecycle.__aexit__, None, None, None)
        self.http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),
            base_url="http://127.0.0.1:8080", headers={"Authorization": "Bearer valid-token"})
        self.addAsyncCleanup(self.http.aclose)

    def client(self, mode="auto", http=None):
        return Client(streamable_http_client("http://127.0.0.1:8080/mcp", http_client=http or self.http), mode=mode)

    async def test_released_client_discovers_and_reads_in_both_protocol_eras(self):
        for mode, protocol in (("auto", "2026-07-28"), ("legacy", "2025-11-25")):
            with self.subTest(mode=mode):
                async with self.client(mode) as client:
                    self.assertEqual(client.protocol_version, protocol)
                    tools = {tool.name: tool for tool in await client.list_tools()}
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
                    self.assertTrue(all(tool.annotations.read_only_hint for tool in tools.values()))
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
        self.assertEqual(results, [principals[name].descriptor() for name in ("first", "second")])
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),
                headers={"Authorization": "Bearer first"}) as http:
            async with self.client(http=http) as client:
                count = len(reads.requests)
                principals.pop("first")
                with self.assertRaises(Exception):
                    await client.call_tool("get_workspace", {"workspace_id": "workspace-a"})
                self.assertEqual(len(reads.requests), count)
