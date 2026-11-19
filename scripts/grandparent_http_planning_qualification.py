"""Actual Operations701 HTTP intent forwarding; no compiler or runtime claim."""
from dataclasses import replace
import unittest
from unittest.mock import Mock

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations.cpk_server import CpkServerPlanningService
from control_plane_kit_operations.deployment_program import DeploymentProgramReference
from control_plane_kit_operations.deployment_program_projections import DeploymentNoChanges
from control_plane_kit_operations.planning import ManagedVerificationPlanningIntent

import test_standard_mcp as fixture
from test_http_mcp_boundaries import _principal


class GrandparentHttpPlanningTests(fixture.StandardMcpFixture, unittest.IsolatedAsyncioTestCase):
    mcp_profile = "grandparent-read-only-v1"

    async def test_http_preserves_managed_intent_fences_and_key_while_mcp_refuses(self):
        intent = ManagedVerificationPlanningIntent.AUTHENTICATED_LOCAL_POSTGRES_AND_HTTP
        program = Mock()
        program.prepare.return_value = DeploymentNoChanges(DeploymentProgramReference("workspace-a", "plan-a"))
        service = CpkServerPlanningService(Mock(), deployment_program=program)
        self.host.services[ControlPlaneServiceRole.PLANNING].handle = service.handle
        self.host.verifier.authenticate = lambda credential: replace(_principal(), workspace_grants=(WorkspaceGrant(
            "workspace-a", (PolicyScope.INSTANCE_WORKSPACE_READ, PolicyScope.INSTANCE_WORKSPACE_EDIT, PolicyScope.PLAN_REQUEST)),))
        payload = dict(draft_id="draft-a", revision=7,
            expected_current=dict(authored_graph_id="graph-current", realized_projection_id="projection-current"),
            expected_desired=dict(authored_graph_id="graph-saved", realized_projection_id="projection-saved"),
            expected_desired_graph_revision=3, title="Managed saved preparation", idempotency_key="managed-http-key",
            managed_verification=intent.value)
        response = await self.http.post("/workspaces/workspace-a/deployments/prepare", json=payload)
        self.assertEqual(response.status_code, 200)
        request = program.prepare.call_args.args[0]
        self.assertIs(request.managed_verification, intent)
        self.assertEqual((request.desired.draft_id, request.desired.revision), ("draft-a", 7))
        self.assertEqual(request.expected_current.authored_graph_id, "graph-current")
        self.assertEqual(request.expected_desired.realized_projection_id, "projection-saved")
        self.assertEqual(request.expected_desired_graph_revision, 3)
        self.assertEqual(request.idempotency_key.value, "managed-http-key")
        async with self.client() as client:
            result = await client.call_tool("prepare_deployment", {"workspace_id": "workspace-a", **payload})
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["error"]["status"], 404)
        self.assertEqual(program.prepare.call_count, 1)
