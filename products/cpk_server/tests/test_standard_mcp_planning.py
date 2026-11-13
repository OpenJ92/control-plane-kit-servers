"""MCP command composition; actual durable proof stays in packaged owner gate."""
from dataclasses import replace
import unittest
from unittest.mock import Mock

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations.cpk_server import CpkServerPlanningService
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
