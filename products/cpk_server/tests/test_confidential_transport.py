"""Real ASGI byte/ordering laws and neutral MCP argument admission."""
import asyncio
from contextlib import redirect_stderr, redirect_stdout
import importlib
import io
import json
import unittest
from unittest.mock import patch

from control_plane_kit_core.operations import ControlPlaneServiceRole, HTTP_ONLY_COMMAND_ROUTE_IDS
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations.cpk_server import CpkServerProvisionConflict

import test_http_host as host_fixture
from cpk_http_host_fixtures import fixture
from test_secret_provider_bootstrap import _base_environment


MCP_LIMIT = 1_048_576
INTAKE = "/workspaces/workspace-a/secret-material/provision"
SENTINEL = "synthetic-confidential-value-never-for-output"


def mcp_headers(token="valid-token", method="tools/call"):
    return {"Accept": "application/json", "MCP-Protocol-Version": "2025-06-18",
            "Mcp-Method": method, "Authorization": "Bearer " + token}


def read_message():
    return {"jsonrpc": "2.0", "id": "read-a", "method": "resources/read",
            "params": {"name": "read.run-events", "arguments": {
                "workspace_id": "workspace-a", "run_id": "run-a"}}}


def padded_json(value, size):
    body = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if len(body) > size:
        raise AssertionError("test body exceeds requested size")
    return body + b" " * (size - len(body))


class ConfidentialTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.host = host_fixture.CpkHttpHostTests("test_every_operator_contract_reaches_unchanged_auth_boundary")
        self.host.setUp()
        self.addCleanup(self.host.tearDown)
        self.app = self.host.app

    async def invoke(self, path, chunks, *, method="POST", headers=None, query=b"", app=None,
                     receive_error=None):
        headers = {"Authorization": "Bearer valid-token"} if headers is None else headers
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                 "http_version": "1.1", "method": method, "scheme": "http", "path": path,
                 "raw_path": path.encode("ascii"), "query_string": query, "root_path": "",
                 "headers": [(name.lower().encode("ascii"), value.encode("ascii")) for name, value in headers.items()],
                 "server": ("test", 80), "client": ("127.0.0.1", 1234)}
        messages, received = [], []
        async def receive():
            if receive_error is not None:
                raise receive_error
            index = len(received)
            if index >= len(chunks):
                raise AssertionError("unexpected receive after final request frame")
            received.append(index)
            return {"type": "http.request", "body": chunks[index], "more_body": index + 1 < len(chunks)}
        async def send(message):
            messages.append(message)
        await (app or self.app)(scope, receive, send)
        starts = [item for item in messages if item["type"] == "http.response.start"]
        self.assertEqual(len(starts), 1)
        body = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
        return starts[0]["status"], json.loads(body), len(received)

    def clear_records(self):
        self.host.verifier.credentials.clear()
        for service in self.host.services.values():
            service.requests.clear()

    def assert_no_dispatch(self):
        self.assertEqual(sum(len(service.requests) for service in self.host.services.values()), 0)

    async def test_http_route_and_auth_refuse_before_receive(self):
        for path, token, expected in (("/workspaces/unknown/unknown", "valid-token", 404),
                                      (INTAKE, "rejected", 401)):
            with self.subTest(path=path, status=expected):
                self.clear_records()
                status, body, reads = await self.invoke(path, [b"invalid JSON"],
                    headers={"Authorization": "Bearer " + token})
                self.assertEqual(status, expected)
                self.assertEqual(body, {"error": {"status": expected,
                    "message": "unknown route" if expected == 404 else "invalid credential"}})
                self.assertEqual(reads, 0)
                self.assertEqual(self.host.verifier.credentials, [] if expected == 404 else [b"rejected"])
                self.assert_no_dispatch()

    async def test_http_actual_chunk_budgets_ignore_content_length_and_stop_on_overflow(self):
        for path, limit in (("/workspaces", 65_536), (INTAKE, 98_304)):
            for declared in (None, "1", "999999999"):
                with self.subTest(path=path, declared=declared):
                    headers = {"Authorization": "Bearer valid-token"}
                    if declared is not None:
                        headers["Content-Length"] = declared
                    self.clear_records()
                    body = padded_json({"value": "é🔑"}, limit)
                    # Split a multibyte encoding; decoding must wait for the joined bounded bytes.
                    split = body.index("é".encode("utf-8")) + 1
                    status, _, reads = await self.invoke(path, [body[:split], body[split:]], headers=headers)
                    self.assertEqual((status, reads), (200, 2))
                    self.assertEqual(self.host.verifier.credentials, [b"valid-token"])
                    self.assertEqual(sum(len(item.requests) for item in self.host.services.values()), 1)
                    self.clear_records()
                    status, result, reads = await self.invoke(path, [body, b" ", b"TRAILING-MUST-NOT-BE-PULLED"], headers=headers)
                    self.assertEqual((status, result), (413, {"error": {"status": 413, "message": "request body too large"}}))
                    self.assertEqual(reads, 2)
                    self.assertEqual(self.host.verifier.credentials, [b"valid-token"])
                    self.assert_no_dispatch()

    async def test_http_competing_invalid_framing_preserves_byte_api_precedence(self):
        boundary = self.app.state.http_boundary
        cases = (
            ("GET", "/workspaces/workspace-a/runs/run-a/events", [b"x", b"trailing"], b"x" * 2000, 1),
            ("POST", "/workspaces", [b"bad" * 30000, b"trailing"], b"forbidden=yes", 0),
        )
        for method, path, chunks, query, expected_reads in cases:
            with self.subTest(method=method):
                self.clear_records()
                expected = boundary.handle(method=method, path=path, headers={"Authorization": "Bearer valid-token"},
                                           body=b"".join(chunks), query_string=query)
                self.clear_records()
                status, result, reads = await self.invoke(path, chunks, method=method, query=query)
                self.assertEqual((status, result), (expected.status, expected.body))
                self.assertEqual(reads, expected_reads)
                self.assertEqual(self.host.verifier.credentials, [b"valid-token"])
                self.assert_no_dispatch()
        self.clear_records()
        status, _, reads = await self.invoke("/workspaces/workspace-a/runs/run-a/events", [b"", b""],
                                            method="GET", query=b"x" * 2000)
        self.assertEqual((status, reads), (413, 2))
        self.assert_no_dispatch()

    async def test_host_does_not_use_unbounded_request_body(self):
        from starlette.requests import Request
        with patch.object(Request, "body", side_effect=AssertionError("unbounded body collector invoked")):
            status, _, _ = await self.invoke("/workspaces", [b"{}"])
            self.assertEqual(status, 200)
            status, _, _ = await self.invoke("/mcp", [json.dumps(read_message()).encode()],
                headers=mcp_headers(method="resources/read"))
            self.assertEqual(status, 200)

    async def test_mcp_inclusive_envelope_byte_cap_and_no_trailing_pull(self):
        for declared in (None, "1", "999999999"):
            with self.subTest(declared=declared):
                headers = mcp_headers(method="resources/read")
                if declared is not None:
                    headers["Content-Length"] = declared
                body = padded_json(read_message(), MCP_LIMIT)
                self.clear_records()
                status, _, reads = await self.invoke("/mcp", [body[:31], body[31:]], headers=headers)
                self.assertEqual((status, reads), (200, 2))
                self.assertEqual(self.host.verifier.credentials, [b"valid-token"])
                self.clear_records()
                status, result, reads = await self.invoke("/mcp", [body, b" ", b"trailing"], headers=headers)
                self.assertEqual((status, result), (413, {"error": {"status": 413, "message": "request body too large"}}))
                self.assertEqual(reads, 2)
                self.assertEqual(self.host.verifier.credentials, [])
                self.assert_no_dispatch()

    async def test_mcp_below_cap_parse_header_auth_order_and_overflow_precedence(self):
        cases = (
            ([b"invalid JSON"], {"Authorization": "Bearer rejected"}, 400, "invalid JSON request body", []),
            ([json.dumps(read_message()).encode()], {}, 400, "missing MCP Accept header", []),
            ([json.dumps(read_message()).encode()], mcp_headers("rejected", "resources/read"), 401, "invalid credential", [b"rejected"]),
            ([b"x" * (MCP_LIMIT + 1), b"trailing"], {}, 413, "request body too large", []),
        )
        for chunks, headers, code, message, credentials in cases:
            with self.subTest(code=code, message=message):
                self.clear_records()
                status, result, reads = await self.invoke("/mcp", chunks, headers=headers)
                self.assertEqual((status, result), (code, {"error": {"status": code, "message": message}}))
                self.assertEqual(reads, 1)
                self.assertEqual(self.host.verifier.credentials, credentials)
                self.assert_no_dispatch()

    async def test_representative_maximum_command_frames_and_unicode_fit_mcp_envelope(self):
        for token in ("x", "é🔑"):
            with self.subTest(token=token):
                arguments = dict(workspace_id="workspace-a", run_id="run-a", activity_id="activity-a",
                                 prior_attempt=1, claim_generation=1, idempotency_key="")
                remaining = 65_536 - len(json.dumps(arguments, ensure_ascii=True).encode())
                encoded_width = len(json.dumps(token, ensure_ascii=True)) - 2
                arguments["idempotency_key"] = token * (remaining // encoded_width) + "x" * (remaining % encoded_width)
                self.assertEqual(len(json.dumps(arguments, ensure_ascii=True).encode()), 65_536)
                message = {"jsonrpc": "2.0", "id": "max-command", "method": "tools/call",
                           "params": {"name": "command.deployment.reobserve-connector", "arguments": arguments}}
                for escaped in (False, True):
                    self.clear_records()
                    body = json.dumps(message, ensure_ascii=escaped).encode("utf-8")
                    self.assertLess(len(body), MCP_LIMIT)
                    status, _, _ = await self.invoke("/mcp", [body[:29], body[29:]], headers=mcp_headers())
                    self.assertEqual(status, 200)
                    requests = self.host.services[ControlPlaneServiceRole.EXECUTION].requests
                    self.assertEqual(len(requests), 1)
                    self.assertEqual(len(requests[0].payload["idempotency_key"]), len(arguments["idempotency_key"]))

    async def test_safe_conflict_status_and_unexpected_error_do_not_reflect_payload(self):
        service = self.host.services[ControlPlaneServiceRole.EXECUTION]
        body = json.dumps({"value_base64": SENTINEL}).encode()
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), \
                patch.object(service, "handle", side_effect=ValueError(SENTINEL)):
            status, result, _ = await self.invoke(INTAKE, [body])
        self.assertEqual((status, result), (500, {"error": {"status": 500, "message": "application service failed"}}))
        self.assertNotIn(SENTINEL, output.getvalue() + repr(result))
        with patch.object(service, "handle", side_effect=CpkServerProvisionConflict("workspace-a", "request-a")):
            status, result, _ = await self.invoke(INTAKE, [body])
        self.assertEqual((status, result), (409, {"error": {"status": 409,
            "message": "provision request already exists", "status_reference": {
                "route_id": "read.secret-material-provision", "workspace_id": "workspace-a", "request_id": "request-a"}}}))
        status, result, _ = await self.invoke("/workspaces/workspace-a/secret-material-provisions/request-a", [b""], method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(result["route_id"], "read.secret-material-provision")
        self.assertNotIn(SENTINEL, repr(result))

    async def test_real_default_production_composition_keeps_provision_unavailable(self):
        server = self.host.server
        config = server.CpkServerBootstrapConfiguration.from_environment({**_base_environment(),
            "CPK_RUNTIME_INTERPRETERS": "none", "CPK_CONTROL_AUTH_VERIFIER": "static-development",
            "CPK_CONTROL_AUTH_STATIC_CREDENTIAL": "synthetic-operator",
            "CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON": json.dumps({"workspace-a": [item.value for item in PolicyScope]})})
        with patch.object(server, "_install_operations_schema"), \
                patch.object(server.psycopg, "connect", side_effect=AssertionError("unexpected database IO")) as database:
            app = server.create_app(config, server._credential_verifier(config), control=fixture().config,
                                    principal_authorizer=server._configured_principal_authorizer(config), clock=lambda: 150)
            status, _, _ = await self.invoke(INTAKE, [b"{}"], app=app,
                headers={"Authorization": "Bearer synthetic-operator"})
            self.assertEqual(status, 501)
            database.assert_not_called()

    async def test_cancellation_during_collection_is_not_normalized_to_overflow(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.invoke(INTAKE, [], receive_error=asyncio.CancelledError())
        self.assert_no_dispatch()

    def test_http_only_mcp_route_is_rejected_before_arguments_access(self):
        boundary = self.app.state.mcp_boundary
        accesses = []
        class PoisonParams(dict):
            def get(self, key, default=None):
                if key == "arguments":
                    accesses.append(key)
                    raise AssertionError("HTTP-only arguments accessed")
                return super().get(key, default)
        for route_id in HTTP_ONLY_COMMAND_ROUTE_IDS:
            for method in ("tools/call", "resources/read"):
                with self.subTest(route=route_id, method=method):
                    response = boundary.handle(headers=mcp_headers(method=method), message={
                        "jsonrpc": "2.0", "id": "forbidden", "method": method,
                        "params": PoisonParams(name=route_id)})
                    self.assertEqual((response.status, response.body), (404, {"error": {
                        "status": 404, "message": "unknown MCP operation"}}))
        self.assertEqual(accesses, [])
        self.assert_no_dispatch()
        parity = boundary.composition.handoff.command_parity.commands
        self.assertFalse(any(item.http_route_id in HTTP_ONLY_COMMAND_ROUTE_IDS for item in parity))

    def test_confidential_service_request_repr_omits_payload(self):
        boundary = importlib.import_module("control_plane_kit_servers_cpk_server.boundary")
        request = boundary.CpkServerServiceRequest("http", "command.secret-material.provision",
            ControlPlaneServiceRole.EXECUTION, {"workspace_id": "workspace-a"},
            {"value_base64": SENTINEL}, self.host.verifier.authenticate(b"valid-token"))
        self.assertNotIn(SENTINEL, repr(request))
        self.assertIn("command.secret-material.provision", repr(request))
