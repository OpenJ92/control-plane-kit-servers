"""Real host/Operations join; coordinator records commands, not durable effects."""
import asyncio
import importlib
import inspect
import secrets
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from control_plane_kit_core.identity import (
    AuthenticatedPrincipal, PrincipalIdentity, PrincipalKind, WorkspaceGrant,
)
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations.cpk_server import (
    CpkServerExecutionService, CpkServerOperationsApplication,
)
from cpk_http_host_fixtures import fixture
from test_http_mcp_boundaries import RecordingService


PRODUCT_SRC = Path(__file__).resolve().parents[1] / "src"


class RecordingCoordinator:
    def __init__(self):
        self.calls = []
        self.completed = []
        self.sync_calls = 0
        self.entered = asyncio.Event()
        self.release = None
        self.cancelled = False
        self.failure = None

    async def _record(self, kind, command):
        self.calls.append((kind, command))
        self.entered.set()
        try:
            if self.release is not None:
                await self.release.wait()
            else:
                await asyncio.sleep(0)
            if self.failure is not None:
                raise self.failure
            self.completed.append(kind)
            return SimpleNamespace(descriptor=lambda: {"outcome": "recorded", "kind": kind})
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def execute_managed(self, command):
        return await self._record("execute", command)

    async def reobserve(self, command):
        return await self._record("reobserve", command)

    def execute(self, command):
        self.sync_calls += 1
        raise AssertionError("the host entered legacy synchronous execution")


class AwaitedExecutionHostTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        sys.path.insert(0, str(PRODUCT_SRC))
        self.addCleanup(self._remove_product_imports)
        self.server = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        boundary = importlib.import_module("control_plane_kit_servers_cpk_server.boundary")
        for owner in (boundary.CpkServerHttpProcessBoundary, boundary.CpkServerMcpProcessBoundary):
            self.assertTrue(inspect.iscoroutinefunction(getattr(owner, "handle_async", None)),
                            "the shared process boundary has no awaited entrance")
        auth = importlib.import_module("control_plane_kit_servers_cpk_server.authentication")
        self.coordinator = RecordingCoordinator()
        services = {role: RecordingService(role.value) for role in ControlPlaneServiceRole}
        services[ControlPlaneServiceRole.EXECUTION] = CpkServerExecutionService(self.coordinator)
        self.operations = CpkServerOperationsApplication(services)
        self.principals = {
            name: AuthenticatedPrincipal(
                PrincipalIdentity("https://identity.example.invalid", name, kind),
                (WorkspaceGrant("workspace-a", scopes),),
            )
            for name, kind, scopes in (
                ("worker", PrincipalKind.WORKER, (PolicyScope.EXECUTION_OPERATE,)),
                ("operator", PrincipalKind.OPERATOR, (PolicyScope.EXECUTION_OPERATE,)),
                ("unprivileged", PrincipalKind.WORKER, ()),
            )
        }
        # Ephemeral local fixture credentials, never operator/provider authority.
        self.credentials = {name: secrets.token_hex(24) for name in self.principals}
        verifier = auth.StaticDevelopmentMultiCredentialVerifier(tuple(
            auth.StaticDevelopmentPrincipalCredential(self.credentials[name].encode(), principal)
            for name, principal in self.principals.items()
        ))
        config = self.server.CpkServerBootstrapConfiguration.from_environment({
            "CPK_SERVER_MODE": "execution-capable", "CPK_CONTROL_AUTH_CONFIGURED": "true",
            "CPK_PORT": "8080", "CPK_RUNTIME_INTERPRETERS": "none",
            **{f"CPK_{store}_DATABASE_URL": "postgres://fixture:fixture@database.invalid/db"
               for store in ("WORKPLACE", "ACTIVITY_HISTORY", "OBSERVER_STATE", "GRAPH_TOPOLOGY")},
        })
        control = fixture()
        # Replace only effectful construction. The host, verifier, application,
        # execution service, authority parsing and command constructors are real.
        with patch.object(self.server, "_operations_application", return_value=self.operations):
            self.app = self.server.create_app(config, verifier, control=control.config, clock=lambda: 150)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    @staticmethod
    def _remove_product_imports():
        sys.path.remove(str(PRODUCT_SRC))
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith("control_plane_kit_servers_cpk_server."):
                sys.modules.pop(name, None)

    def payload(self, operation="reobserve"):
        payload = {"claim_generation": 1, "idempotency_key": "transport-test"}
        if operation == "reobserve":
            payload.update(activity_id="observe:" + "a" * 64, prior_attempt=1)
        else:
            payload["max_effects"] = 1
        return payload

    def wire(self, surface, operation="reobserve", payload=None, *, principal="worker", workspace="workspace-a"):
        payload = self.payload(operation) if payload is None else payload
        route_id = "command.deployment." + ("reobserve-connector" if operation == "reobserve" else "execute")
        composition = self.app.state.http_boundary.composition
        route = composition.http_api.route(route_id)
        headers = {"Authorization": "Bearer " + self.credentials.get(principal, "invalid-fixture-credential")}
        if surface == "http":
            return (route.path_template.replace("{workspace_id}", workspace).replace("{run_id}", "run-a"),
                    payload, headers)
        binding = next(item for item in composition.handoff.command_parity.commands if item.http_route_id == route_id)
        headers.update({"Accept": "application/json", "MCP-Protocol-Version": "2025-06-18", "Mcp-Method": "tools/call"})
        return "/mcp", {"jsonrpc": "2.0", "id": "transport", "method": "tools/call",
            "params": {"name": binding.mcp_tool_name,
                       "arguments": {"workspace_id": workspace, "run_id": "run-a", **payload}}}, headers

    async def call(self, surface, operation="reobserve", payload=None, **options):
        path, document, headers = self.wire(surface, operation, payload, **options)
        return await self.client.post(path, json=document, headers=headers)

    async def test_execute_and_reobserve_reach_real_service_with_identical_actor_context(self):
        for operation in ("execute", "reobserve"):
            for surface in ("http", "mcp"):
                with self.subTest(operation=operation, surface=surface):
                    response = await self.call(surface, operation)
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json() if surface == "http" else response.json()["result"]
                    self.assertEqual(result, {"outcome": "recorded", "kind": operation})
                    kind, command = self.coordinator.calls[-1]
                    self.assertEqual(kind, operation)
                    self.assertEqual(command.context, self.principals["worker"].command_context("workspace-a"))
                    self.assertEqual(command.execution.run_id, "run-a")
                    self.assertEqual(command.execution.authority.worker_id, "worker")
                    self.assertEqual(command.execution.fence.worker_id, "worker")
                    self.assertEqual(command.execution.fence.generation, 1)
                    self.assertEqual(command.execution.max_effects, 1)
                    self.assertEqual(command.execution.idempotency_key.value, "transport-test")
                    if operation == "reobserve":
                        self.assertEqual(command.predecessor.activity_id, "observe:" + "a" * 64)
                        self.assertEqual(command.predecessor.attempt, 1)
            self.assertEqual(self.coordinator.calls[-2][1], self.coordinator.calls[-1][1])
        self.assertEqual(self.coordinator.completed, ["execute", "execute", "reobserve", "reobserve"])
        self.assertEqual(self.coordinator.sync_calls, 0)

    async def test_host_waits_for_actual_async_completion(self):
        for surface in ("http", "mcp"):
            self.coordinator.entered.clear()
            self.coordinator.release = asyncio.Event()
            task = asyncio.create_task(self.call(surface))
            try:
                await asyncio.wait_for(self.coordinator.entered.wait(), 2)
                self.assertFalse(task.done())
                self.coordinator.release.set()
                self.assertEqual((await asyncio.wait_for(task, 2)).status_code, 200)
            finally:
                if not task.done():
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
        self.assertEqual(self.coordinator.completed, ["reobserve", "reobserve"])
        self.assertEqual(self.coordinator.sync_calls, 0)

    async def test_auth_workspace_and_principal_kind_refuse_before_coordinator(self):
        for surface in ("http", "mcp"):
            for operation in ("execute", "reobserve"):
                for options, status in (({"principal": "invalid"}, 401),
                        ({"principal": "operator"}, 403), ({"principal": "unprivileged"}, 403),
                        ({"workspace": "foreign-workspace"}, 403)):
                    with self.subTest(surface=surface, operation=operation, options=options):
                        self.assertEqual((await self.call(surface, operation, **options)).status_code, status)
        self.assertEqual(self.coordinator.calls, [])
        self.assertEqual(self.coordinator.sync_calls, 0)

    async def test_reobserve_closed_fields_and_operations_numeric_laws(self):
        candidates = []
        for name in self.payload():
            candidate = self.payload()
            candidate.pop(name)
            candidates.append(candidate)
        for name, values in (("prior_attempt", (True, 0, -1, 2**31, "1", 1.5)),
                ("claim_generation", (True, 0, -1, 2**63, "1")),
                ("activity_id", ("", "bad activity", None)),
                ("idempotency_key", ("", "x" * 201, None))):
            candidates.extend({**self.payload(), name: value} for value in values)
        candidates.extend({**self.payload(), name: value} for name, value in (
            ("extra", "ignored"), ("max_effects", 2), ("actor_id", "another-worker"),
            ("permissions", {"execution.operate": True}), ("scopes", ["execution.operate"])))
        for surface in ("http", "mcp"):
            for index, payload in enumerate(candidates):
                with self.subTest(surface=surface, case=index):
                    response = await self.call(surface, payload=payload)
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertLess(len(response.content), 1024)
        self.assertEqual(self.coordinator.calls, [])
        self.assertEqual(self.coordinator.sync_calls, 0)

    async def test_http_body_cannot_override_path_identity(self):
        for name in ("workspace_id", "run_id"):
            response = await self.call("http", payload={**self.payload(), name: "foreign"})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.coordinator.calls, [])

    async def test_oversized_reobserve_is_rejected_before_coordinator(self):
        for surface in ("http", "mcp"):
            response = await self.call(surface, payload={**self.payload(), "idempotency_key": "x" * 65537})
            self.assertEqual(response.status_code, 413)
        self.assertEqual(self.coordinator.calls, [])

    async def test_authenticated_malformed_shape_and_unauthenticated_input_stay_bounded(self):
        path, _, headers = self.wire("http")
        for raw in (b"[]", b"null", b"not-json"):
            response = await self.client.post(path, content=raw, headers=headers)
            self.assertEqual(response.status_code, 400)
            rejected = await self.client.post(path, content=raw, headers={"Authorization": "Bearer invalid"})
            self.assertEqual(rejected.status_code, 401)
        _, _, mcp_headers = self.wire("mcp")
        self.assertEqual((await self.client.post("/mcp", json=[], headers=mcp_headers)).status_code, 400)
        self.assertEqual(self.coordinator.calls, [])

    async def test_unexpected_coordinator_error_remains_bounded_internal_failure(self):
        self.coordinator.failure = RuntimeError("private-test-marker")
        for surface in ("http", "mcp"):
            response = await self.call(surface)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json(), {"error": {"message": "application service failed", "status": 500}})
            self.assertNotIn("private-test-marker", response.text)
        self.assertEqual(self.coordinator.completed, [])
        self.assertEqual(self.coordinator.sync_calls, 0)

    async def test_cancellation_propagates_to_awaited_coordinator_without_detached_work(self):
        for surface in ("http", "mcp"):
            self.coordinator.entered.clear()
            self.coordinator.cancelled = False
            self.coordinator.release = asyncio.Event()
            task = asyncio.create_task(self.call(surface))
            try:
                await asyncio.wait_for(self.coordinator.entered.wait(), 2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertTrue(self.coordinator.cancelled)
                self.assertEqual(self.coordinator.completed, [])
            finally:
                if not task.done():
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
        self.assertEqual(len(self.coordinator.calls), 2)
        self.assertEqual(self.coordinator.sync_calls, 0)
