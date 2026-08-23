from __future__ import annotations

import unittest
from unittest.mock import call, patch

from control_plane_kit_core.verification import VerificationPolicy

from scripts import cpk_server_hosted_activity


class HostedActivityReadinessTests(unittest.TestCase):
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
