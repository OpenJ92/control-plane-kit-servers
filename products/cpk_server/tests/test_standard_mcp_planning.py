"""MCP command composition; actual durable proof stays in packaged owner gate."""
from dataclasses import replace
import unittest
from unittest.mock import MagicMock, Mock

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations.cpk_server import CpkServerPlanningService, CpkServerReadService
from control_plane_kit_operations.deployment_program_interpreter import DeploymentProgramAuthorizationDenied, DeploymentProgramStateConflict
from control_plane_kit_operations.deployment_program import DeploymentProgramReference, SavedDesiredTopologyRevision
from control_plane_kit_operations.deployment_program_projections import DeploymentNoChanges

import test_standard_mcp as fixture
from test_http_mcp_boundaries import _principal


class StandardMcpPlanningTests(fixture.StandardMcpFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.program = Mock()
        self.program.prepare.return_value = DeploymentNoChanges(DeploymentProgramReference("workspace-a", "plan-a"))
        service = CpkServerPlanningService(Mock(), deployment_program=self.program)
        self.host.services[ControlPlaneServiceRole.PLANNING].handle = service.handle
        self.scopes = (PolicyScope.INSTANCE_WORKSPACE_READ, PolicyScope.INSTANCE_WORKSPACE_EDIT, PolicyScope.PLAN_REQUEST)
        self.host.verifier.authenticate = lambda credential: replace(_principal(), workspace_grants=(
            WorkspaceGrant("workspace-a", self.scopes),))

    def arguments(self):
        return {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 7,
            "expected_current": {"authored_graph_id": "graph-current", "realized_projection_id": "projection-current"},
            "expected_desired": {"authored_graph_id": "graph-saved", "realized_projection_id": "projection-saved"},
            "expected_desired_graph_revision": 3, "title": "Saved fixture preparation", "idempotency_key": "mcp-domain-key"}

    async def test_prepare_tool_preserves_typed_saved_input_fences_key_and_http_result(self):
        async with self.client() as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertIn("prepare_deployment", tools)
            self.assertFalse(tools["prepare_deployment"].annotations.read_only_hint)
            self.assertFalse(tools["prepare_deployment"].annotations.destructive_hint)
            self.assertIn("idempotency_key", tools["prepare_deployment"].input_schema["required"])
            self.assertIn("list_session_plans", tools)
            result = await client.call_tool("prepare_deployment", self.arguments())
            self.assertFalse(result.is_error, result.structured_content)
            command = self.program.prepare.call_args.args[0]
            self.assertIs(type(command.desired), SavedDesiredTopologyRevision)
            self.assertEqual((command.desired.draft_id, command.desired.revision), ("draft-a", 7))
            self.assertEqual(command.idempotency_key.value, "mcp-domain-key")
            self.assertEqual(command.expected_desired_graph_revision, 3)
            self.assertEqual(command.expected_current.authored_graph_id, "graph-current")
            self.assertEqual(command.expected_desired.realized_projection_id, "projection-saved")
            body = {key: value for key, value in self.arguments().items() if key != "workspace_id"}
            http = await self.http.post("/workspaces/workspace-a/deployments/prepare", json=body)
            self.assertEqual(http.status_code, 200)
            self.assertEqual(result.structured_content, http.json())
            self.assertEqual(self.program.prepare.call_args.args[0], command)

    async def test_missing_planning_permission_and_unsupported_intent_do_not_prepare(self):
        async with self.client() as client:
            self.scopes = (PolicyScope.INSTANCE_WORKSPACE_READ, PolicyScope.INSTANCE_WORKSPACE_EDIT)
            denied = await client.call_tool("prepare_deployment", self.arguments())
            self.assertTrue(denied.is_error)
            self.assertEqual(denied.structured_content["error"]["status"], 403)
            self.program.prepare.assert_not_called()
            self.scopes += (PolicyScope.PLAN_REQUEST,)
            for extra in ({"managed_verification": {"profile": "unsupported"}},
                          {"session_id": "caller-invented-session"}, {"desired_graph": {}},
                          {"approval": True}):
                refused = await client.call_tool("prepare_deployment", {**self.arguments(), **extra})
                self.assertTrue(refused.is_error)
                self.assertEqual(refused.structured_content["error"]["status"], 400)
            self.program.prepare.assert_not_called()

    async def test_owner_failures_stay_bounded_and_never_trigger_an_automatic_retry(self):
        async with self.client() as client:
            for error, status in ((DeploymentProgramAuthorizationDenied("synthetic-private-canary"), 403),
                                  (DeploymentProgramStateConflict("synthetic-private-canary"), 409),
                                  (RuntimeError("synthetic-private-canary"), 500)):
                self.program.prepare.reset_mock()
                self.program.prepare.side_effect = error
                result = await client.call_tool("prepare_deployment", self.arguments())
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content["error"]["status"], status)
                self.assertNotIn("synthetic-private-canary", str(result.structured_content))
                self.assertEqual(self.program.prepare.call_count, 1)

    async def test_runtime_delivery_diagnostic_requires_its_own_permission(self):
        from control_plane_kit_operations.records import WorkspaceRecord
        from control_plane_kit_operations.read_pages import ReadPage
        unit = MagicMock()
        unit.__enter__.return_value = unit
        unit.stores.workspaces.get.return_value = WorkspaceRecord("workspace-a", "Fixture")
        unit.stores.runtime_authority_deliveries.active_page.side_effect = lambda request: ReadPage.from_candidates(request, ())
        factory = Mock(return_value=unit)
        self.host.services[ControlPlaneServiceRole.READS].handle = CpkServerReadService(factory).handle
        async with self.client() as client:
            arguments = {"workspace_id": "workspace-a"}
            denied = await client.call_tool("list_runtime_authority_deliveries", arguments)
            self.assertTrue(denied.is_error)
            self.assertEqual(denied.structured_content["error"]["status"], 403)
            factory.assert_not_called()
            self.scopes += (PolicyScope.RUNTIME_AUTHORITY_DELIVERY_READ,)
            result = await client.call_tool("list_runtime_authority_deliveries", arguments)
            self.assertFalse(result.is_error, result.structured_content)
            http = await self.http.get("/workspaces/workspace-a/runtime-authority-deliveries")
            self.assertEqual(http.status_code, 200)
            self.assertEqual(result.structured_content, http.json())
            self.assertEqual(result.structured_content["items"], [])
