"""MCP command composition; actual durable proof stays in packaged owner gate."""
from dataclasses import replace
import json
import unittest
from unittest.mock import MagicMock, Mock
import httpx2

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations.cpk_server import CpkServerPlanningService, CpkServerReadService
from control_plane_kit_operations.deployment_program_interpreter import DeploymentProgramAuthorizationDenied, DeploymentProgramStateConflict
from control_plane_kit_operations.deployment_program import DeploymentProgramReference, SavedDesiredTopologyRevision
from control_plane_kit_operations.deployment_program_projections import DeploymentNoChanges
from control_plane_kit_operations.planning import HttpVerificationPlanningIntent, ManagedVerificationPlanningIntent

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
            self.assertIsNone(command.http_verification_intent)
            self.assertIsNone(command.managed_verification)
            self.assertEqual(command.expected_desired_graph_revision, 3)
            self.assertEqual(command.expected_current.authored_graph_id, "graph-current")
            self.assertEqual(command.expected_desired.realized_projection_id, "projection-saved")
            body = {key: value for key, value in self.arguments().items() if key != "workspace_id"}
            http = await self.http.post("/workspaces/workspace-a/deployments/prepare", json=body)
            self.assertEqual(http.status_code, 200)
            self.assertEqual(result.structured_content, http.json())
            self.assertEqual(self.program.prepare.call_args.args[0], command)

    async def test_saved_readiness_choices_reach_the_same_typed_command_as_http(self):
        cases = (
            ("http_verification_intent", HttpVerificationPlanningIntent.AUTHENTICATED_SAMPLES),
            ("managed_verification", ManagedVerificationPlanningIntent.AUTHENTICATED_LOCAL_POSTGRES_AND_HTTP),
        )
        async with self.client() as client:
            for field, intent in cases:
                with self.subTest(field=field):
                    args = {**self.arguments(), field: intent.value}
                    body = {key: value for key, value in args.items() if key != "workspace_id"}
                    http = await self.http.post("/workspaces/workspace-a/deployments/prepare", json=body)
                    self.assertEqual(http.status_code, 200)
                    command = self.program.prepare.call_args.args[0]
                    self.assertIs(getattr(command, field), intent)
                    self.program.prepare.reset_mock()
                    result = await client.call_tool("prepare_deployment", args)
                    self.assertFalse(result.is_error, result.structured_content)
                    self.assertEqual(result.structured_content, http.json())
                    self.program.prepare.assert_called_once_with(command)

    async def test_missing_planning_permission_and_unsupported_intent_do_not_prepare(self):
        async with self.client() as client:
            self.scopes = (PolicyScope.INSTANCE_WORKSPACE_READ, PolicyScope.INSTANCE_WORKSPACE_EDIT)
            denied = await client.call_tool("prepare_deployment", self.arguments())
            self.assertTrue(denied.is_error)
            self.assertEqual(denied.structured_content["error"]["status"], 403)
            self.program.prepare.assert_not_called()
            self.scopes += (PolicyScope.PLAN_REQUEST,)
            planning = self.host.services[ControlPlaneServiceRole.PLANNING]
            planning.handle = Mock(wraps=planning.handle)
            for extra in ({"managed_verification": {"profile": "unsupported"}},
                          {"managed_verification": "unsupported"}, {"http_verification_intent": None},
                          {"http_verification_intent": "unsupported"}, {"managed_verification": None},
                          {"http_verification_intent": "authenticated-samples",
                           "managed_verification": "authenticated-local-postgres-and-http"},
                          {"session_id": "caller-invented-session"}, {"desired_graph": {}},
                          {"approval": True}):
                refused = await client.call_tool("prepare_deployment", {**self.arguments(), **extra})
                self.assertTrue(refused.is_error)
                self.assertEqual(refused.structured_content["error"]["status"], 400)
            planning.handle.assert_not_called()
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

    async def test_response_loss_is_handled_across_sdk_teardown_without_hiding_other_errors(self):
        class FixtureResponseLost(httpx2.ReadError):
            """Fixture-only marker, distinct from other transport failures."""

        async def exercise(error):
            count, dropped, handled = 0, False, False
            async def lose_response(response):
                nonlocal count, dropped
                frame = json.loads(response.request.content) if response.request.method == "POST" else {}
                if frame.get("method") == "tools/call" and frame.get("params", {}).get("name") == "prepare_deployment":
                    count += 1
                    await response.aread()
                    dropped = True
                    raise error
            try:
                async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),
                        headers={"Authorization": "Bearer valid-token"}, event_hooks={"response": [lose_response]}) as http:
                    async with self.client(http=http) as client:
                        await client.list_tools()
                        await client.call_tool("prepare_deployment", self.arguments())
                        self.fail("response loss was not reported")
            except* FixtureResponseLost:
                self.assertTrue(dropped)
                handled = True
            self.assertEqual(count, 1)
            return handled

        self.assertTrue(await exercise(FixtureResponseLost("synthetic fixture response loss")))
        self.assertEqual(self.program.prepare.call_count, 1)
        self.program.prepare.reset_mock()
        foreign = httpx2.ReadError("unrelated transport failure")
        with self.assertRaises(BaseExceptionGroup) as caught:
            await exercise(foreign)
        self.assertIsNotNone(caught.exception.subgroup(lambda error: error is foreign))
        self.assertEqual(self.program.prepare.call_count, 1)


class StandardMcpAdmissionTests(fixture.StandardMcpFixture, unittest.IsolatedAsyncioTestCase):
    async def test_operator_submission_preserves_http_owner_command_and_receipt(self):
        from control_plane_kit_operations.cpk_server import CpkServerAdmissionService
        from control_plane_kit_core.operations import ControlPlaneServiceRole

        args = {"workspace_id": "workspace-a", "session_id": "session-a", "plan_id": "plan-a",
                "approval_request_id": "approval-a", "idempotency_key": "admit-a",
                "readiness": [{"activity_id": "act_" + "a" * 24, "evidence_ref": "operator/db-ready"}]}
        receipt = {"workspace_id": "workspace-a", "session_id": "session-a", "plan_id": "plan-a",
                   "execution_request_id": "request-a", "action_id": "action-a", "action_ordinal": 2,
                   "replayed": False, "status": "queued"}
        owner = Mock()
        owner.execute.return_value.descriptor.return_value = receipt
        self.host.services[ControlPlaneServiceRole.ADMISSION].handle = CpkServerAdmissionService(owner).handle
        scopes = (PolicyScope.PLAN_EXECUTE,)
        self.host.verifier.authenticate = lambda credential: replace(_principal(), workspace_grants=(
            WorkspaceGrant("workspace-a", scopes),))
        async with self.client() as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            self.assertIn("admit_deployment", tools)
            self.assertFalse(tools["admit_deployment"].annotations.read_only_hint)
            self.assertTrue(tools["admit_deployment"].annotations.destructive_hint)
            self.assertTrue({"decide_approval", "claim_run", "start_run", "execute_deployment"}.isdisjoint(tools))
            result = await client.call_tool("admit_deployment", args)
            self.assertEqual(result.structured_content, receipt)
            mcp_command = owner.execute.call_args.args[0]
            self.assertEqual(mcp_command.actor_id, "operator-jacob")
            self.assertEqual(mcp_command.actor_scopes, scopes)
            http = await self.http.post("/workspaces/workspace-a/plans/plan-a/admission",
                json={k: v for k, v in args.items() if k not in ("workspace_id", "plan_id")})
            self.assertEqual((http.status_code, http.json()), (200, receipt))
            self.assertEqual(owner.execute.call_args.args[0], mcp_command)
            self.assertEqual(mcp_command.readiness[0].evidence_ref, "operator/db-ready")
            for fields in ({"actor_scopes": ["plan:execute"]}, {"actor_id": "other"}, {"approval": True},
                           {"readiness": [{"activity_id": "a", "value": "private"}]}):
                self.assertEqual((await client.call_tool("admit_deployment", {**args, **fields})).structured_content["error"]["status"], 400)
            scopes = (PolicyScope.INSTANCE_WORKSPACE_READ,)
            self.assertEqual((await client.call_tool("admit_deployment", args)).structured_content["error"]["status"], 403)
            self.assertEqual(owner.execute.call_count, 2)
