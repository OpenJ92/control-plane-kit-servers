from __future__ import annotations

import unittest
from unittest.mock import call, patch

from control_plane_kit_core.verification import VerificationPolicy

from scripts import cpk_server_hosted_activity


class HostedActivityReadinessTests(unittest.TestCase):
    def test_execution_lifecycle_preserves_fence_and_projection_coordinates(
        self,
    ) -> None:
        workflow = cpk_server_hosted_activity.HostedWorkflow(
            "http://cpk-server",
            workspace_id="candidate-topology-1714",
            worker_id="worker-a",
            server_container="candidate-server",
        )

        with (
            patch.object(
                cpk_server_hosted_activity,
                "_mcp_tool",
                side_effect=(
                    {
                        "ready_for_execution": True,
                        "plan_id": "plan-a",
                        "base_realized_projection_id": "projection-current",
                        "desired_realized_projection_id": "projection-desired",
                        "desired_graph_revision": 3,
                    },
                    {"coordinator_status": "completed"},
                ),
            ) as tool,
            patch.object(
                cpk_server_hosted_activity,
                "_http",
                side_effect=(
                    {"run_id": "run-a", "claim_generation": 7},
                    {},
                    {"to_graph_id": "graph-desired"},
                ),
            ) as request,
        ):
            plan_id = workflow.plan_transition(
                session_id="session-a",
                title="Hello",
                current_graph_id="graph-current",
                desired_graph_id="graph-desired",
            )
            run_id = workflow.claim(title="Hello", request_id="request-a")
            workflow.start_run(title="Hello", run_id=run_id)
            workflow.execute_to_completion(run_id, sync_runtime_networks=False)
            advanced_graph_id = workflow.advance_current_graph(
                title="Hello",
                run_id=run_id,
                plan_id=plan_id,
                current_graph_id="graph-current",
                desired_graph_id="graph-desired",
            )

        self.assertEqual(advanced_graph_id, "graph-desired")
        self.assertEqual(
            tool.call_args_list[1],
            call(
                "http://cpk-server",
                "command.deployment.execute",
                {
                    "workspace_id": "candidate-topology-1714",
                    "run_id": "run-a",
                    "worker_id": "worker-a",
                    "actor_scopes": ["execution:operate"],
                    "claim_generation": 7,
                    "idempotency_key": "candidate-topology-1714:execute:0",
                    "max_effects": 1,
                },
                timeout=60,
                authorization="Bearer worker-present",
            ),
        )
        self.assertEqual(
            request.call_args_list[1],
            call(
                "http://cpk-server",
                "POST",
                "/workspaces/candidate-topology-1714/runs/run-a/start",
                {
                    "worker_id": "worker-a",
                    "actor_scopes": ["execution:operate"],
                    "claim_generation": 7,
                    "idempotency_key": "candidate-topology-1714:Hello:start",
                },
                extra_headers={"Authorization": "Bearer worker-present"},
            ),
        )
        self.assertEqual(
            request.call_args_list[2],
            call(
                "http://cpk-server",
                "POST",
                "/workspaces/candidate-topology-1714/runs/run-a/advance-current-graph",
                {
                    "plan_id": "plan-a",
                    "expected_current_graph_id": "graph-current",
                    "expected_current_realized_projection_id": "projection-current",
                    "desired_graph_id": "graph-desired",
                    "desired_realized_projection_id": "projection-desired",
                    "expected_desired_graph_revision": 3,
                    "worker_id": "worker-a",
                    "actor_scopes": ["execution:operate"],
                    "claim_generation": 7,
                    "idempotency_key": "candidate-topology-1714:Hello:advance",
                },
                extra_headers={"Authorization": "Bearer worker-present"},
            ),
        )

    def test_run_claim_uses_current_bounded_lease_contract(self) -> None:
        workflow = cpk_server_hosted_activity.HostedWorkflow(
            "http://cpk-server",
            workspace_id="candidate-topology-1714",
            worker_id="worker-a",
            server_container="candidate-server",
        )

        with patch.object(
            cpk_server_hosted_activity,
            "_http",
            return_value={"run_id": "run-a", "claim_generation": 1},
        ) as request:
            run_id = workflow.claim(title="Hello", request_id="request-a")

        self.assertEqual(run_id, "run-a")
        request.assert_called_once_with(
            "http://cpk-server",
            "POST",
            "/workspaces/candidate-topology-1714/runs/request-a/claim",
            {
                "worker_id": "worker-a",
                "actor_scopes": ["execution:operate"],
                "lease_duration_seconds": 1800,
                "idempotency_key": "candidate-topology-1714:Hello:claim",
            },
            extra_headers={"Authorization": "Bearer worker-present"},
        )

    def test_pending_approval_mcp_read_uses_current_cursor_contract(self) -> None:
        workflow = cpk_server_hosted_activity.HostedWorkflow(
            "http://cpk-server",
            workspace_id="candidate-topology-1714",
            worker_id="worker-a",
            server_container="candidate-server",
        )

        with patch.object(
            cpk_server_hosted_activity,
            "_mcp_read",
            side_effect=(
                {"items": [{"request_id": "approval-a"}]},
                {"plan": {"plan_id": "plan-a"}},
            ),
        ) as mcp:
            workflow.assert_approval_visible("approval-a", "plan-a")

        self.assertEqual(
            mcp.call_args_list,
            [
                call(
                    "http://cpk-server",
                    "read.pending-approvals",
                    {"workspace_id": "candidate-topology-1714", "limit": 10},
                ),
                call(
                    "http://cpk-server",
                    "read.approval-detail",
                    {
                        "workspace_id": "candidate-topology-1714",
                        "approval_id": "approval-a",
                    },
                ),
            ],
        )

    def test_candidate_graph_readback_preserves_distinct_http_and_mcp_surfaces(
        self,
    ) -> None:
        workflow = cpk_server_hosted_activity.HostedWorkflow(
            "http://cpk-server",
            workspace_id="candidate-topology-1714",
            worker_id="worker-a",
            server_container="candidate-server",
        )
        expected = {
            "graph_id": "graph-predecessor",
            "descriptor_sha256": "a" * 64,
        }
        self.assertTrue(
            hasattr(workflow, "read_current_graph_http")
            and hasattr(workflow, "read_current_graph_mcp"),
            "candidate graph readback phases are not implemented",
        )

        with (
            patch.object(
                cpk_server_hosted_activity,
                "_http",
                return_value=expected,
            ) as http,
            patch.object(
                cpk_server_hosted_activity,
                "_mcp_read",
                return_value=expected,
            ) as mcp,
        ):
            observed_http = workflow.read_current_graph_http()
            observed_mcp = workflow.read_current_graph_mcp()

        self.assertEqual(observed_http, expected)
        self.assertEqual(observed_mcp, expected)
        http.assert_called_once_with(
            "http://cpk-server",
            "GET",
            "/workspaces/candidate-topology-1714/graphs/current",
        )
        mcp.assert_called_once_with(
            "http://cpk-server",
            "read.current-graph",
            {"workspace_id": "candidate-topology-1714"},
        )

    def test_candidate_activity_readback_preserves_distinct_http_and_mcp_surfaces(
        self,
    ) -> None:
        workflow = cpk_server_hosted_activity.HostedWorkflow(
            "http://cpk-server",
            workspace_id="candidate-topology-1714",
            worker_id="worker-a",
            server_container="candidate-server",
        )
        expected = {"events": [{"event_id": "event-a"}]}
        self.assertTrue(
            hasattr(workflow, "read_activity_http")
            and hasattr(workflow, "read_activity_mcp"),
            "candidate activity readback phases are not implemented",
        )

        with (
            patch.object(
                cpk_server_hosted_activity,
                "_http",
                return_value=expected,
            ) as http,
            patch.object(
                cpk_server_hosted_activity,
                "_mcp_read",
                return_value=expected,
            ) as mcp,
        ):
            observed_http = workflow.read_activity_http(limit=200)
            observed_mcp = workflow.read_activity_mcp(limit=200)

        self.assertEqual(observed_http, expected)
        self.assertEqual(observed_mcp, expected)
        http.assert_called_once_with(
            "http://cpk-server",
            "GET",
            "/workspaces/candidate-topology-1714/activity?limit=200",
        )
        mcp.assert_called_once_with(
            "http://cpk-server",
            "read.activity",
            {"workspace_id": "candidate-topology-1714", "limit": 200},
        )

    def test_policy_cadence_occurs_only_between_failed_attempts(self) -> None:
        policy = VerificationPolicy(
            timeout_seconds=3.0,
            interval_seconds=1.25,
            maximum_attempts=2,
        )

        with (
            patch.object(
                cpk_server_hosted_activity,
                "_http",
                side_effect=(
                    OSError("not ready"),
                    {"status": "ready", "runtime_interpreters": "docker"},
                ),
            ) as request,
            patch.object(cpk_server_hosted_activity.time, "sleep") as sleep,
        ):
            cpk_server_hosted_activity._wait_ready(
                "http://cpk-server",
                policy=policy,
            )

        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            [item.kwargs["timeout"] for item in request.call_args_list],
            [3.0, 3.0],
        )
        self.assertEqual(sleep.call_args_list, [call(1.25)])

    def test_first_attempt_success_has_no_delay(self) -> None:
        policy = VerificationPolicy(
            interval_seconds=2.0,
            maximum_attempts=3,
        )

        with (
            patch.object(
                cpk_server_hosted_activity,
                "_http",
                return_value={"status": "ready", "runtime_interpreters": "docker"},
            ),
            patch.object(cpk_server_hosted_activity.time, "sleep") as sleep,
        ):
            cpk_server_hosted_activity._wait_ready(
                "http://cpk-server",
                policy=policy,
            )

        sleep.assert_not_called()

    def test_ready_response_with_wrong_runtime_fails_immediately_and_redacted(
        self,
    ) -> None:
        policy = VerificationPolicy(
            interval_seconds=2.0,
            maximum_attempts=3,
        )

        with (
            patch.object(
                cpk_server_hosted_activity,
                "_http",
                return_value={
                    "status": "ready",
                    "runtime_interpreters": "none",
                    "diagnostic": "credential-secret",
                },
            ) as request,
            patch.object(cpk_server_hosted_activity.time, "sleep") as sleep,
        ):
            with self.assertRaises(RuntimeError) as raised:
                cpk_server_hosted_activity._wait_ready(
                    "http://cpk-server/private-address",
                    policy=policy,
                )

        with self.subTest(boundary="single-semantic-attempt"):
            self.assertEqual(request.call_count, 1)
        with self.subTest(boundary="semantic-failure-has-no-delay"):
            self.assertEqual(sleep.call_args_list, [])
        with self.subTest(boundary="fixed-redacted-message"):
            self.assertEqual(
                str(raised.exception),
                "cpk-server did not boot with Docker runtime",
            )

    def test_exhaustion_has_no_trailing_delay(self) -> None:
        policy = VerificationPolicy(
            interval_seconds=1.5,
            maximum_attempts=2,
        )

        with (
            patch.object(
                cpk_server_hosted_activity,
                "_http",
                return_value={"status": "starting"},
            ),
            patch.object(cpk_server_hosted_activity.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "did not become ready"):
                cpk_server_hosted_activity._wait_ready(
                    "http://cpk-server",
                    policy=policy,
                )

        self.assertEqual(sleep.call_args_list, [call(1.5)])


if __name__ == "__main__":
    unittest.main()
