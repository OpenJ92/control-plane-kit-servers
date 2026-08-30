from __future__ import annotations

import inspect
import unittest
from unittest.mock import call, patch

from control_plane_kit_core.verification import VerificationPolicy

from scripts import cpk_server_hosted_activity


class _PrimaryTransportFailure(RuntimeError):
    pass


class HostedActivityReadinessTests(unittest.TestCase):
    @staticmethod
    def _workflow() -> cpk_server_hosted_activity.HostedWorkflow:
        return cpk_server_hosted_activity.HostedWorkflow(
            "http://cpk-server",
            workspace_id="workspace-a",
            worker_id="worker-a",
            server_container="cpk-server",
            worker_authorization="Bearer worker-a",
        )

    def _claimed_type(self) -> type:
        claimed_type = getattr(cpk_server_hosted_activity, "ClaimedRun", None)
        self.assertIsNotNone(claimed_type, "hosted workflow lacks ClaimedRun")
        return claimed_type

    @staticmethod
    def _claim_result(**changes: object) -> dict[str, object]:
        result: dict[str, object] = {
            "execution_request_id": "request-a",
            "run_id": "run-a",
            "run_status": "claimed",
            "event_id": "event-claim",
            "event_type": "run_opened",
            "event_ordinal": 1,
            "action_id": "action-claim",
            "action_type": "claim-run",
            "replayed": False,
            "claim_generation": 7,
        }
        result.update(changes)
        return result

    @staticmethod
    def _start_result(**changes: object) -> dict[str, object]:
        result: dict[str, object] = {
            "execution_request_id": "request-a",
            "run_id": "run-a",
            "run_status": "running",
            "event_id": "event-start",
            "event_type": "run_started",
            "event_ordinal": 2,
            "action_id": "action-start",
            "action_type": "start-run",
            "replayed": False,
            "claim_generation": 7,
        }
        result.update(changes)
        return result

    @staticmethod
    def _execute_result(**changes: object) -> dict[str, object]:
        result: dict[str, object] = {
            "run_id": "run-a",
            "run_status": "running",
            "coordinator_status": "progressed",
            "effects_attempted": 1,
            "activity_id": "activity-a",
        }
        result.update(changes)
        return result

    @staticmethod
    def _advance_result(**changes: object) -> dict[str, object]:
        result: dict[str, object] = {
            "workspace_id": "workspace-a",
            "from_authored_graph_id": "graph-current",
            "from_realized_projection_id": "projection-current",
            "to_authored_graph_id": "graph-desired",
            "to_realized_projection_id": "projection-desired",
            "to_realized_projection_digest": "d" * 64,
            "desired_graph_revision": 2,
            "from_graph_id": "graph-current",
            "to_graph_id": "graph-desired",
            "run_id": "run-a",
            "plan_id": "plan-a",
            "event_id": "event-advance",
            "action_id": "action-advance",
            "replayed": False,
        }
        result.update(changes)
        return result

    @staticmethod
    def _plan_detail(**changes: object) -> dict[str, object]:
        result: dict[str, object] = {
            "workspace_id": "workspace-a",
            "kind": "plan-detail",
            "plan": {
                "plan_id": "plan-a",
                "session_id": "session-a",
                "base_graph_id": "graph-current",
                "desired_graph_id": "graph-desired",
                "base_realized_projection_id": "projection-current",
                "desired_realized_projection_id": "projection-desired",
                "desired_graph_revision": 2,
                "status": "planned",
                "created_at": "2026-08-30T12:00:00Z",
                "payload": {
                    "schema": "control-plane-kit.activity-plan",
                    "version": 1,
                    "activities": [],
                },
                "risk_summary": {
                    "max_risk": "informational",
                    "counts": {
                        "informational": 0,
                        "low": 0,
                        "medium": 0,
                        "high": 0,
                        "critical": 0,
                    },
                    "destructive_count": 0,
                    "review_blocker_count": 0,
                    "ready_for_execution": True,
                },
                "recovery": {
                    "schema": "control-plane-kit.recovery-candidate",
                    "version": 1,
                    "mode": "reverse-transition",
                    "source_graph_name": "graph-desired",
                    "target_graph_name": "graph-current",
                    "plan": {
                        "schema": "control-plane-kit.activity-plan",
                        "version": 1,
                        "activities": [],
                    },
                    "approval": {
                        "required_scope": "plan:approve",
                        "max_risk": "informational",
                        "destructive": False,
                    },
                    "requires_manual_review": False,
                    "assessments": [],
                    "limitations": [
                        {
                            "code": "graph-state-only",
                            "message": (
                                "the candidate is derived from desired graph "
                                "structure, not proof of real-world effect reversal"
                            ),
                        }
                    ],
                },
            },
        }
        result.update(changes)
        return result

    @classmethod
    def _plan_detail_with_plan(cls, **changes: object) -> dict[str, object]:
        result = cls._plan_detail()
        plan = dict(result["plan"])
        plan.update(changes)
        result["plan"] = plan
        return result

    @staticmethod
    def _run_event(
        *,
        event_id: str = "event-a",
        run_id: str = "run-a",
        ordinal: int = 1,
        event_type: str = "run_started",
        activity_id: str | None = None,
        payload: dict[str, object] | None = None,
        recovery: dict[str, object] | None = None,
    ) -> dict[str, object]:
        event: dict[str, object] = {
            "event_id": event_id,
            "run_id": run_id,
            "ordinal": ordinal,
            "event_type": event_type,
            "occurred_at": "2026-08-30T12:00:00Z",
            "activity_id": activity_id,
            "payload": {} if payload is None else payload,
            "failure": None,
        }
        if recovery is not None:
            event["recovery"] = recovery
        return event

    @classmethod
    def _run_event_page(
        cls,
        *,
        workspace_id: str = "workspace-a",
        run_id: str = "run-a",
        limit: int = 100,
        next_cursor: object = None,
    ) -> dict[str, object]:
        return {
            "workspace_id": workspace_id,
            "kind": "run-events",
            "limit": limit,
            "items": [
                cls._run_event(run_id=run_id),
                cls._run_event(
                    event_id="event-b",
                    run_id=run_id,
                    ordinal=2,
                    event_type="step_succeeded",
                    activity_id="start-node:hello-a",
                    payload={"node_id": "hello-a", "outcome": "succeeded"},
                ),
                cls._run_event(
                    event_id="event-c",
                    run_id=run_id,
                    ordinal=3,
                    event_type="recovery_decision_recorded",
                    recovery={
                        "decision": "abandon-expired-claim",
                        "retained_run_id": run_id,
                        "prior_fence": {
                            "worker_id": "worker-a",
                            "generation": 7,
                        },
                        "replacement_fence": None,
                    },
                ),
            ],
            "next_cursor": next_cursor,
        }

    def test_claim_contract_is_closed_and_generation_is_frozen(self) -> None:
        claimed_type = self._claimed_type()
        workflow = self._workflow()
        with patch.object(
            cpk_server_hosted_activity,
            "_http",
            return_value=self._claim_result(),
        ) as request:
            claimed = workflow.claim(title="deploy", request_id="request-a")

        self.assertEqual(claimed, claimed_type("run-a", 7))
        with self.assertRaises(AttributeError):
            claimed.claim_generation = 8
        self.assertEqual(
            request.call_args.args[3],
            {
                "worker_id": "worker-a",
                "actor_scopes": ["execution:operate"],
                "lease_duration_seconds": 600,
                "idempotency_key": "workspace-a:deploy:claim",
            },
        )
        self.assertNotIn("lease_expires_at", request.call_args.args[3])

        with patch.object(
            cpk_server_hosted_activity,
            "_http",
            return_value=self._claim_result(replayed=True),
        ):
            replayed = workflow.claim(title="deploy", request_id="request-a")
        self.assertEqual(replayed, claimed_type("run-a", 7))

        missing = self._claim_result()
        missing.pop("claim_generation")
        hostile = (
            missing,
            self._claim_result(claim_generation=None),
            self._claim_result(claim_generation=True),
            self._claim_result(claim_generation=0),
            self._claim_result(claim_generation=-1),
            self._claim_result(claim_generation=2**63),
            self._claim_result(claim_generation="7"),
            self._claim_result(execution_request_id="request-foreign"),
            self._claim_result(run_id=""),
            self._claim_result(run_status="running"),
            self._claim_result(event_id=""),
            self._claim_result(event_type="run_started"),
            self._claim_result(event_ordinal=True),
            self._claim_result(action_id=""),
            self._claim_result(action_type="start-run"),
            self._claim_result(replayed=0),
            self._claim_result(unexpected="truth"),
        )
        for response in hostile:
            with self.subTest(response=response):
                with patch.object(
                    cpk_server_hosted_activity,
                    "_http",
                    return_value=response,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "^claim result is invalid$",
                    ) as raised:
                        self._workflow().claim(
                            title="deploy",
                            request_id="request-a",
                        )
                self.assertEqual(str(raised.exception), "claim result is invalid")

    def test_start_contract_uses_frozen_generation_and_exact_evidence(self) -> None:
        claimed = self._claimed_type()("run-a", 7)
        self.assertIn(
            "claimed_run",
            inspect.signature(
                cpk_server_hosted_activity.HostedWorkflow.start_run
            ).parameters,
        )
        with patch.object(
            cpk_server_hosted_activity,
            "_http",
            return_value=self._start_result(),
        ) as request:
            self._workflow().start_run(title="deploy", claimed_run=claimed)

        self.assertEqual(request.call_args.args[3]["claim_generation"], 7)
        with patch.object(
            cpk_server_hosted_activity,
            "_http",
            return_value=self._start_result(replayed=True),
        ):
            self._workflow().start_run(title="deploy", claimed_run=claimed)

        hostile = (
            self._start_result(execution_request_id=""),
            self._start_result(run_id="run-foreign"),
            self._start_result(run_status="claimed"),
            self._start_result(event_id=""),
            self._start_result(event_type="run_opened"),
            self._start_result(event_ordinal=1),
            self._start_result(action_id=""),
            self._start_result(action_type="claim-run"),
            self._start_result(replayed=1),
            self._start_result(claim_generation=6),
            self._start_result(unexpected="truth"),
        )
        for response in hostile:
            with self.subTest(response=response):
                with patch.object(
                    cpk_server_hosted_activity,
                    "_http",
                    return_value=response,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "^start result is invalid$",
                    ) as raised:
                        self._workflow().start_run(
                            title="deploy",
                            claimed_run=claimed,
                        )
                self.assertEqual(str(raised.exception), "start result is invalid")

    def test_execute_accepts_only_closed_current_coordinator_results(self) -> None:
        claimed = self._claimed_type()("run-a", 7)
        self.assertIn(
            "claimed_run",
            inspect.signature(
                cpk_server_hosted_activity.HostedWorkflow.execute_to_completion
            ).parameters,
        )
        with (
            patch.object(
                cpk_server_hosted_activity,
                "_mcp_tool",
                side_effect=(
                    self._execute_result(),
                    self._execute_result(
                        coordinator_status="in-flight",
                        effects_attempted=0,
                    ),
                    self._execute_result(
                        run_status="succeeded",
                        coordinator_status="completed",
                        effects_attempted=0,
                        activity_id=None,
                    ),
                ),
            ) as execute,
            patch.object(cpk_server_hosted_activity.time, "sleep") as sleep,
        ):
            self._workflow().execute_to_completion(
                claimed_run=claimed,
                sync_runtime_networks=False,
            )

        self.assertEqual(execute.call_count, 3)
        self.assertEqual(
            [item.args[2]["claim_generation"] for item in execute.call_args_list],
            [7, 7, 7],
        )
        sleep.assert_not_called()

        hostile = (
            self._execute_result(
                run_status="completed",
                coordinator_status="completed",
                effects_attempted=0,
                activity_id=None,
            ),
            self._execute_result(run_id="run-foreign"),
            self._execute_result(effects_attempted=True),
            self._execute_result(unexpected="truth"),
        )
        for index, response in enumerate(hostile):
            with self.subTest(case=index):
                with patch.object(
                    cpk_server_hosted_activity,
                    "_mcp_tool",
                    return_value=response,
                ) as execute:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "^execution result is invalid$",
                    ) as raised:
                        self._workflow().execute_to_completion(
                            claimed_run=claimed,
                            sync_runtime_networks=False,
                        )
                self.assertEqual(execute.call_count, 1)
                self.assertEqual(str(raised.exception), "execution result is invalid")

        for status in ("failed", "uncertain", "unsupported", "blocked"):
            with self.subTest(status=status):
                with (
                    patch.object(
                        cpk_server_hosted_activity,
                        "_mcp_tool",
                        return_value=self._execute_result(
                            coordinator_status=status,
                            effects_attempted=0,
                            activity_id=None,
                        ),
                    ) as execute,
                    patch.object(cpk_server_hosted_activity, "_http") as timeline,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "^deployment execution stopped$",
                    ) as raised:
                        self._workflow().execute_to_completion(
                            claimed_run=claimed,
                            sync_runtime_networks=False,
                        )
                self.assertEqual(execute.call_count, 1)
                timeline.assert_not_called()
                self.assertEqual(str(raised.exception), "deployment execution stopped")

    def test_advance_contract_carries_and_validates_complete_lineage(self) -> None:
        claimed = self._claimed_type()("run-a", 7)
        self.assertIn(
            "claimed_run",
            inspect.signature(
                cpk_server_hosted_activity.HostedWorkflow.advance_current_graph
            ).parameters,
        )
        workflow = self._workflow()
        workflow._plan_coordinates["plan-a"] = (
            "projection-current",
            "projection-desired",
            2,
        )
        with patch.object(
            cpk_server_hosted_activity,
            "_http",
            return_value=self._advance_result(),
        ) as request:
            advanced = workflow.advance_current_graph(
                title="deploy",
                claimed_run=claimed,
                plan_id="plan-a",
                current_graph_id="graph-current",
                desired_graph_id="graph-desired",
            )

        self.assertEqual(advanced, "graph-desired")
        payload = request.call_args.args[3]
        self.assertEqual(
            {
                key: payload[key]
                for key in (
                    "plan_id",
                    "expected_current_graph_id",
                    "expected_current_realized_projection_id",
                    "desired_graph_id",
                    "desired_realized_projection_id",
                    "expected_desired_graph_revision",
                    "claim_generation",
                )
            },
            {
                "plan_id": "plan-a",
                "expected_current_graph_id": "graph-current",
                "expected_current_realized_projection_id": "projection-current",
                "desired_graph_id": "graph-desired",
                "desired_realized_projection_id": "projection-desired",
                "expected_desired_graph_revision": 2,
                "claim_generation": 7,
            },
        )

        with patch.object(
            cpk_server_hosted_activity,
            "_http",
            return_value=self._advance_result(replayed=True),
        ):
            replayed = workflow.advance_current_graph(
                title="deploy",
                claimed_run=claimed,
                plan_id="plan-a",
                current_graph_id="graph-current",
                desired_graph_id="graph-desired",
            )
        self.assertEqual(replayed, "graph-desired")

        hostile = (
            self._advance_result(workspace_id=""),
            self._advance_result(workspace_id="workspace-foreign"),
            self._advance_result(run_id=""),
            self._advance_result(run_id="run-foreign"),
            self._advance_result(plan_id=""),
            self._advance_result(plan_id="plan-foreign"),
            self._advance_result(from_authored_graph_id=""),
            self._advance_result(from_authored_graph_id="graph-foreign"),
            self._advance_result(from_graph_id="graph-foreign"),
            self._advance_result(
                from_realized_projection_id="projection-foreign"
            ),
            self._advance_result(to_authored_graph_id="graph-foreign"),
            self._advance_result(to_graph_id="graph-foreign"),
            self._advance_result(to_realized_projection_id="projection-foreign"),
            self._advance_result(to_realized_projection_digest=None),
            self._advance_result(desired_graph_revision=3),
            self._advance_result(event_id=""),
            self._advance_result(action_id=""),
            self._advance_result(replayed=0),
            self._advance_result(unexpected="truth"),
        )
        for response in hostile:
            with self.subTest(response=response):
                with patch.object(
                    cpk_server_hosted_activity,
                    "_http",
                    return_value=response,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "^advance result is invalid$",
                    ) as raised:
                        workflow.advance_current_graph(
                            title="deploy",
                            claimed_run=claimed,
                            plan_id="plan-a",
                            current_graph_id="graph-current",
                            desired_graph_id="graph-desired",
                        )
                self.assertEqual(str(raised.exception), "advance result is invalid")

    def test_plan_detail_is_nonpaged_authenticated_and_protocol_equal(self) -> None:
        plan = self._plan_detail()
        with (
            patch.object(
                cpk_server_hosted_activity,
                "_http",
                return_value=plan,
            ) as http,
            patch.object(
                cpk_server_hosted_activity,
                "_mcp",
                return_value=plan,
            ) as mcp,
            patch.object(
                cpk_server_hosted_activity,
                "_mcp_read",
                return_value=plan,
            ),
        ):
            detail = self._workflow().read_plan_detail("plan-a")

        self.assertEqual(detail, plan)
        self.assertIsNotNone(http.call_args, "plan detail omitted HTTP readback")
        self.assertIsNotNone(mcp.call_args, "plan detail omitted MCP readback")
        self.assertEqual(
            http.call_args.args,
            (
                "http://cpk-server",
                "GET",
                "/workspaces/workspace-a/plans/plan-a",
            ),
        )
        self.assertNotIn("?", http.call_args.args[2])
        self.assertNotEqual(http.call_args.kwargs.get("authorize"), False)
        self.assertEqual(
            mcp.call_args.args,
            (
                "http://cpk-server",
                "resources/read",
                "read.plan-detail",
                {"workspace_id": "workspace-a", "plan_id": "plan-a"},
            ),
        )
        self.assertEqual(
            mcp.call_args.kwargs["authorization"],
            cpk_server_hosted_activity.AUTHORIZATION,
        )

        missing_plan_fields = []
        for key in tuple(plan["plan"]):
            incomplete = dict(plan["plan"])
            incomplete.pop(key)
            missing_plan_fields.append({**plan, "plan": incomplete})
        hostile = (
            *[(value, value) for value in missing_plan_fields],
            (
                self._plan_detail(workspace_id="workspace-foreign"),
                self._plan_detail(workspace_id="workspace-foreign"),
            ),
            (
                self._plan_detail(kind="plan-events"),
                self._plan_detail(kind="plan-events"),
            ),
            (
                self._plan_detail_with_plan(plan_id="plan-foreign"),
                self._plan_detail_with_plan(plan_id="plan-foreign"),
            ),
            (
                self._plan_detail_with_plan(payload={}),
                self._plan_detail_with_plan(payload={}),
            ),
            (
                self._plan_detail_with_plan(risk_summary={}),
                self._plan_detail_with_plan(risk_summary={}),
            ),
            (
                self._plan_detail_with_plan(recovery={}),
                self._plan_detail_with_plan(recovery={}),
            ),
            (self._plan_detail(unexpected="truth"), plan),
            (plan, self._plan_detail_with_plan(status="superseded")),
        )
        for index, (http_detail, mcp_detail) in enumerate(hostile):
            with self.subTest(case=index):
                with (
                    patch.object(
                        cpk_server_hosted_activity,
                        "_http",
                        return_value=http_detail,
                    ),
                    patch.object(
                        cpk_server_hosted_activity,
                        "_mcp",
                        return_value=mcp_detail,
                    ),
                    patch.object(
                        cpk_server_hosted_activity,
                        "_mcp_read",
                        return_value=mcp_detail,
                    ),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "^plan detail is invalid$",
                    ) as raised:
                        self._workflow().read_plan_detail("plan-a")
                self.assertEqual(str(raised.exception), "plan detail is invalid")

    def test_run_events_are_exact_bounded_and_protocol_equal(self) -> None:
        reader = getattr(
            cpk_server_hosted_activity.HostedWorkflow,
            "read_run_events",
            None,
        )
        self.assertIsNotNone(reader, "hosted workflow lacks run-event reads")
        page = self._run_event_page()
        with (
            patch.object(
                cpk_server_hosted_activity,
                "_http",
                return_value=page,
            ) as http,
            patch.object(
                cpk_server_hosted_activity,
                "_mcp",
                return_value=page,
            ) as mcp,
        ):
            events = self._workflow().read_run_events("run-a", limit=100)

        self.assertEqual(events, tuple(page["items"]))
        self.assertIsNotNone(http.call_args, "run events omitted HTTP readback")
        self.assertIsNotNone(mcp.call_args, "run events omitted MCP readback")
        self.assertEqual(
            http.call_args.args,
            (
                "http://cpk-server",
                "GET",
                "/workspaces/workspace-a/runs/run-a/events?limit=100",
            ),
        )
        self.assertNotEqual(http.call_args.kwargs.get("authorize"), False)
        self.assertEqual(
            mcp.call_args.args,
            (
                "http://cpk-server",
                "resources/read",
                "read.run-events",
                {"workspace_id": "workspace-a", "run_id": "run-a", "limit": 100},
            ),
        )
        self.assertEqual(
            mcp.call_args.kwargs["authorization"],
            cpk_server_hosted_activity.AUTHORIZATION,
        )

        for invalid_limit in (True, 0, 101):
            with self.subTest(invalid_limit=invalid_limit):
                with (
                    patch.object(cpk_server_hosted_activity, "_http") as http,
                    patch.object(cpk_server_hosted_activity, "_mcp") as mcp,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "^run event limit is invalid$",
                    ) as raised:
                        self._workflow().read_run_events(
                            "run-a",
                            limit=invalid_limit,
                        )
                http.assert_not_called()
                mcp.assert_not_called()
                self.assertEqual(str(raised.exception), "run event limit is invalid")

        duplicate = self._run_event_page()
        duplicate["items"] = [duplicate["items"][0], duplicate["items"][0]]
        descending = self._run_event_page()
        descending["items"] = [
            self._run_event(event_id="event-b", ordinal=2),
            self._run_event(event_id="event-a", ordinal=1),
        ]
        oversized = self._run_event_page()
        oversized["items"] = [
            self._run_event(event_id=f"event-{index}", ordinal=index + 1)
            for index in range(101)
        ]
        malformed = self._run_event_page()
        malformed["items"] = [{"event_id": "event-a", "run_id": "run-a"}]
        foreign_event = self._run_event_page()
        foreign_event["items"] = list(foreign_event["items"])
        foreign_event["items"][0] = self._run_event(run_id="run-foreign")
        unexpected_event = self._run_event_page()
        unexpected_event["items"] = list(unexpected_event["items"])
        unexpected_event["items"][0] = {
            **unexpected_event["items"][0],
            "unexpected": "truth",
        }
        noncanonical_timestamp = self._run_event_page()
        noncanonical_timestamp["items"] = list(noncanonical_timestamp["items"])
        noncanonical_timestamp["items"][0] = {
            **noncanonical_timestamp["items"][0],
            "occurred_at": "2026-08-30T12:00:00+00:00",
        }
        malformed_recovery = self._run_event_page()
        malformed_recovery["items"] = list(malformed_recovery["items"])
        malformed_recovery["items"][2] = {
            **malformed_recovery["items"][2],
            "recovery": {},
        }
        secret_event = self._run_event_page()
        secret_event["items"] = list(secret_event["items"])
        secret_event["items"][0] = {
            **secret_event["items"][0],
            "unexpected": {
                "token": "token-not-for-output",
                "endpoint": "http://private.example",
            },
        }
        divergent = self._run_event_page()
        divergent["items"] = list(divergent["items"])
        divergent["items"][1] = {
            **divergent["items"][1],
            "event_type": "run_failed",
        }
        hostile = (
            ({}, page),
            (malformed, malformed),
            (foreign_event, foreign_event),
            (unexpected_event, unexpected_event),
            (noncanonical_timestamp, noncanonical_timestamp),
            (malformed_recovery, malformed_recovery),
            (secret_event, secret_event),
            (self._run_event_page(workspace_id="workspace-foreign"), page),
            (self._run_event_page(run_id="run-foreign"), page),
            ({**page, "kind": "activity"}, {**page, "kind": "activity"}),
            ({**page, "limit": 99}, {**page, "limit": 99}),
            ({**page, "unexpected": "truth"}, page),
            (self._run_event_page(next_cursor={"position": "more"}), page),
            (duplicate, duplicate),
            (descending, descending),
            (oversized, oversized),
            (page, divergent),
        )
        for index, (http_page, mcp_page) in enumerate(hostile):
            with self.subTest(case=index):
                with (
                    patch.object(
                        cpk_server_hosted_activity,
                        "_http",
                        return_value=http_page,
                    ),
                    patch.object(
                        cpk_server_hosted_activity,
                        "_mcp",
                        return_value=mcp_page,
                    ),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "^run events are invalid$",
                    ) as raised:
                        self._workflow().read_run_events("run-a", limit=100)
                self.assertEqual(str(raised.exception), "run events are invalid")
                self.assertNotIn("token-not-for-output", str(raised.exception))
                self.assertNotIn("private.example", str(raised.exception))

    def test_dual_protocol_reads_preserve_primary_failures_and_redact(self) -> None:
        cases = (
            (
                "plan-detail",
                lambda workflow: workflow.read_plan_detail("plan-a"),
                self._plan_detail(),
                "plan detail read failed",
            ),
            (
                "run-events",
                lambda workflow: workflow.read_run_events("run-a", limit=100),
                self._run_event_page(),
                "run event read failed",
            ),
        )
        for owner, invoke, successful, expected_message in cases:
            for failed_protocol in ("http", "mcp"):
                with self.subTest(owner=owner, failed_protocol=failed_protocol):
                    primary = _PrimaryTransportFailure(
                        "raw-response-not-for-output from http://private.example "
                        "token-not-for-output credential-not-for-output"
                    )
                    http_result: object = successful
                    mcp_result: object = successful
                    if failed_protocol == "http":
                        http_result = primary
                    else:
                        mcp_result = primary
                    with (
                        patch.object(
                            cpk_server_hosted_activity,
                            "_http",
                            side_effect=(
                                http_result
                                if isinstance(http_result, BaseException)
                                else None
                            ),
                            return_value=(
                                None
                                if isinstance(http_result, BaseException)
                                else http_result
                            ),
                        ) as http,
                        patch.object(
                            cpk_server_hosted_activity,
                            "_mcp",
                            side_effect=(
                                mcp_result
                                if isinstance(mcp_result, BaseException)
                                else None
                            ),
                            return_value=(
                                None
                                if isinstance(mcp_result, BaseException)
                                else mcp_result
                            ),
                        ) as mcp,
                        patch.object(
                            cpk_server_hosted_activity,
                            "_mcp_read",
                            return_value=successful,
                        ),
                    ):
                        try:
                            invoke(self._workflow())
                        except BaseException as error:
                            caught = error
                        else:
                            self.fail("dual-protocol read failure was swallowed")

                    self.assertIs(type(caught), RuntimeError)
                    self.assertEqual(str(caught), expected_message)
                    self.assertIs(caught.__cause__, primary)
                    self.assertLessEqual(len(str(caught)), 96)
                    for forbidden in (
                        "raw-response-not-for-output",
                        "private.example",
                        "token-not-for-output",
                        "credential-not-for-output",
                    ):
                        self.assertNotIn(forbidden, str(caught))
                        self.assertNotIn(forbidden, repr(caught))
                    if failed_protocol == "http":
                        http.assert_called_once()
                        mcp.assert_not_called()
                    else:
                        http.assert_called_once()
                        mcp.assert_called_once()

    def test_stale_generation_is_one_call_no_advance_and_primary_redacted(self) -> None:
        claimed = self._claimed_type()("run-a", 7)
        primary = _PrimaryTransportFailure(
            "stale generation from http://private.example "
            "token-not-for-output credential-not-for-output payload-not-for-output"
        )
        with patch.object(
            cpk_server_hosted_activity,
            "_mcp_tool",
            side_effect=primary,
        ) as execute:
            with self.assertRaisesRegex(
                RuntimeError,
                "deployment execution failed",
            ) as raised:
                self._workflow().execute_to_completion(
                    claimed_run=claimed,
                    sync_runtime_networks=False,
                )
        self.assertEqual(execute.call_count, 1)
        self.assertIs(raised.exception.__cause__, primary)
        rendered = str(raised.exception)
        for forbidden in (
            "private.example",
            "token-not-for-output",
            "credential-not-for-output",
            "payload-not-for-output",
        ):
            self.assertNotIn(forbidden, rendered)

        workflow = self._workflow()
        with (
            patch.object(workflow, "start_session", return_value="session-a"),
            patch.object(workflow, "set_desired_graph", return_value="graph-desired"),
            patch.object(workflow, "plan_transition", return_value="plan-a"),
            patch.object(
                workflow,
                "request_approval",
                return_value={"request_id": "approval-a"},
            ),
            patch.object(workflow, "assert_approval_visible"),
            patch.object(workflow, "approve"),
            patch.object(workflow, "admit", return_value="request-a"),
            patch.object(workflow, "claim", return_value=claimed),
            patch.object(workflow, "start_run"),
            patch.object(
                workflow,
                "execute_to_completion",
                side_effect=RuntimeError("claim generation is stale"),
            ) as execute_transition,
            patch.object(workflow, "advance_current_graph") as advance,
        ):
            with self.assertRaisesRegex(RuntimeError, "generation is stale"):
                workflow.run_approved_transition(
                    title="deploy",
                    graph=object(),
                    current_graph_id="graph-current",
                )
        execute_transition.assert_called_once()
        advance.assert_not_called()

    def test_persisted_claim_generation_uses_the_same_strict_decoder(self) -> None:
        claimed_type = self._claimed_type()
        decoder = getattr(claimed_type, "from_descriptor", None)
        self.assertIsNotNone(decoder, "ClaimedRun lacks persisted-state decoder")
        claimed = decoder({"run_id": "run-a", "claim_generation": 7})
        self.assertEqual(claimed, claimed_type("run-a", 7))
        self.assertEqual(
            claimed.descriptor(),
            {"run_id": "run-a", "claim_generation": 7},
        )

        hostile = (
            {},
            {"run_id": "run-a"},
            {"claim_generation": 7},
            {"run_id": "", "claim_generation": 7},
            {"run_id": "run-a", "claim_generation": True},
            {"run_id": "run-a", "claim_generation": 0},
            {"run_id": "run-a", "claim_generation": -1},
            {"run_id": "run-a", "claim_generation": 2**63},
            {"run_id": "run-a", "claim_generation": "7"},
            {"run_id": "run-a", "claim_generation": 7, "unexpected": "truth"},
        )
        for state in hostile:
            with self.subTest(state=state):
                with self.assertRaisesRegex(
                    (TypeError, ValueError, RuntimeError),
                    "claim|generation|state",
                ):
                    decoder(state)

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
