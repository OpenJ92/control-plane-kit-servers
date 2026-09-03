from __future__ import annotations

from hashlib import sha256
import importlib
import io
import inspect
import json
from pathlib import Path
import unittest
from unittest.mock import call, patch
from urllib.parse import quote_from_bytes
from uuid import uuid4

from control_plane_kit_core.verification import VerificationPolicy

from scripts import cpk_server_hosted_activity


class _PrimaryTransportFailure(RuntimeError):
    pass


class _PublicConvergenceFixture:
    """Small public-route fixture; CPK owns the command semantics behind it."""

    def __init__(
        self,
        case: unittest.TestCase,
        *,
        attention_status: str | None = None,
        observation_fault: str | None = None,
    ) -> None:
        self.case = case
        self.workspace_id = f"workspace-{uuid4().hex[:12]}"
        self.operator_bearer = f"Bearer operator-{uuid4().hex}"
        self.worker_bearer = f"Bearer worker-{uuid4().hex}"
        self.approver_bearer = f"Bearer approver-{uuid4().hex}"
        self.approver_scopes = {"plan:approve", "plan:approve-destructive"}
        self.router_observation = None
        self.attention_status = attention_status
        self.observation_fault = observation_fault
        self.calls: list[dict[str, object]] = []
        self.coordinates: dict[str, str] = {}
        self.execute_calls = 0
        self.completed = False
        self.approved = False
        self.transition = -1
        self.current_graph_id = f"graph-{uuid4().hex}"
        self.current_projection_id = f"projection-{uuid4().hex}"
        self.current_descriptor: dict[str, object] = {
            "name": self.workspace_id,
            "runtimes": {},
            "nodes": {},
            "edges": {},
            "public_ingresses": [],
        }
        self.pending_descriptor = self.current_descriptor
        self.desired_graph_id: str | None = None
        self.desired_projection_id: str | None = None
        self.desired_revision = 0

    def invoke(
        self,
        route_id: str,
        arguments: dict[str, object],
        *,
        authorization: str,
    ) -> dict[str, object]:
        worker_routes = {
            "command.run.claim",
            "command.run.start",
            "command.deployment.execute",
            "command.graph.advance-current",
        }
        self.case.assertEqual(
            authorization,
            self.approver_bearer if route_id == "command.approval.decide" else
            self.worker_bearer if route_id in worker_routes else self.operator_bearer,
            f"wrong trusted principal for {route_id}",
        )
        self._expect(arguments, workspace_id=self.workspace_id)
        call_record = {
            "route_id": route_id,
            "arguments": json.loads(json.dumps(arguments)),
            "authorization": authorization,
            "transition": self.transition,
        }
        self.calls.append(call_record)
        if route_id == "command.workspace.create":
            return {"workspace": self._workspace()}
        if route_id in {
            "command.product.import",
            "command.runtime-authority.register",
            "command.runtime-authority-delivery.register",
        }:
            return {"status": "accepted"}
        if route_id == "read.workspace":
            return {"workspace": self._workspace()}
        if route_id == "read.current-graph":
            return {
                "workspace_id": self.workspace_id,
                "kind": "current-graph",
                "graph_id": self.current_graph_id,
                "authored_graph_id": self.current_graph_id,
                "realized_projection_id": self.current_projection_id,
                "graph_descriptor": self.current_descriptor,
            }
        if route_id == "command.deployment.prepare":
            self._expect(
                arguments,
                expected_current={
                    "authored_graph_id": self.current_graph_id,
                    "realized_projection_id": self.current_projection_id,
                },
                expected_desired=(
                    None if self.desired_graph_id is None else {
                        "authored_graph_id": self.desired_graph_id,
                        "realized_projection_id": self.desired_projection_id,
                    }
                ),
                expected_desired_graph_revision=self.desired_revision,
            )
            self.transition += 1
            call_record["transition"] = self.transition
            self.coordinates = {
                key: f"{key}-{uuid4().hex}"
                for key in ("plan", "session", "approval", "request", "run")
            }
            self.execute_calls = 0
            self.completed = False
            self.approved = False
            desired = arguments["desired_graph"]
            if desired == self.current_descriptor:
                return {
                    "status": "no-changes",
                    "workspace_id": self.workspace_id,
                    "plan_id": self.coordinates["plan"],
                }
            self.pending_descriptor = desired
            self.desired_revision += 1
            self.desired_graph_id = f"graph-{uuid4().hex}"
            self.desired_projection_id = f"projection-{uuid4().hex}"
            return {
                "status": "approval-required",
                "workspace_id": self.workspace_id,
                "plan_id": self.coordinates["plan"],
                "approval_request_id": self.coordinates["approval"],
            }
        if route_id == "read.plan-detail":
            self._expect(arguments, plan_id=self.coordinates["plan"])
            # Representative public plan output, not a fixture planner. The router
            # has a health activity only in the initial and rewire submissions.
            activities = []
            if self.transition in {0, 2}:
                router_id = next(iter(self.pending_descriptor["edges"].values()))["consumer"]["role"]
                activities.append({
                    "activity_id": f"health-{uuid4().hex}",
                    "operation": {"kind": "wait-for-healthy", "target": {"kind": "node", "node_id": router_id}},
                    "dependencies": [], "risk": "low", "impact": "non-destructive",
                })
            return {
                "workspace_id": self.workspace_id,
                "kind": "plan-detail",
                "plan": {
                    "plan_id": self.coordinates["plan"],
                    "session_id": self.coordinates["session"],
                    "base_graph_id": self.current_graph_id,
                    "desired_graph_id": self.desired_graph_id,
                    "base_realized_projection_id": self.current_projection_id,
                    "desired_realized_projection_id": self.desired_projection_id,
                    "desired_graph_revision": self.desired_revision,
                    "risk_summary": {
                        "destructive_count": 1 if self.transition in {3, 5} else 0,
                    },
                    "payload": {"activities": activities},
                },
            }
        if route_id == "read.approval-detail":
            self._expect(arguments, approval_id=self.coordinates["approval"])
            destructive = self.transition in {3, 5}
            return {
                "approval": {
                    "request_id": self.coordinates["approval"],
                    "session_id": self.coordinates["session"],
                    "required_scope": (
                        "plan:approve-destructive" if destructive else "plan:approve"
                    ),
                    "destructive": destructive,
                    "state": "approved" if self.approved else "pending",
                    "requested_by": "convergence-operator",
                    "decision": None if not self.approved else {
                        "decision_id": f"decision-{uuid4().hex}", "actor_id": "convergence-approver",
                        "decision": "approved", "scope": "plan:approve-destructive" if destructive else "plan:approve",
                        "decided_at": "2026-09-03T12:00:00+00:00",
                    },
                }
            }
        if route_id == "command.approval.decide":
            self._expect(
                arguments,
                approval_id=self.coordinates["approval"],
                session_id=self.coordinates["session"],
                decision="approved",
            )
            required = (
                "plan:approve-destructive" if self.transition in {3, 5}
                else "plan:approve"
            )
            self.case.assertIn(required, self.approver_scopes)
            self.case.assertNotEqual(authorization, self.operator_bearer)
            self.approved = True
            return {"state": "approved", "replayed": False}
        if route_id == "command.deployment.admit":
            self._expect(
                arguments,
                plan_id=self.coordinates["plan"],
                session_id=self.coordinates["session"],
                approval_request_id=self.coordinates["approval"],
            )
            return {
                "execution_request_id": self.coordinates["request"],
                "replayed": False,
            }
        if route_id == "command.run.claim":
            self._expect(arguments, run_id=self.coordinates["request"])
            self.claim_generation = self.transition + 41
            return {
                "run_id": self.coordinates["run"],
                "claim_generation": self.claim_generation,
                "replayed": False,
            }
        if route_id == "command.run.start":
            self._expect(
                arguments, run_id=self.coordinates["run"],
                claim_generation=self.claim_generation,
            )
            return {"run_status": "running", "replayed": False}
        if route_id == "command.deployment.execute":
            self._expect(
                arguments, run_id=self.coordinates["run"],
                claim_generation=self.claim_generation, max_effects=1,
            )
            self.execute_calls += 1
            self.case.assertLessEqual(self.execute_calls, 2)
            if self.attention_status is not None:
                return {
                    "run_id": self.coordinates["run"],
                    "run_status": "running",
                    "coordinator_status": self.attention_status,
                    "effects_attempted": 1,
                    "activity_id": f"activity-{self.transition}",
                }
            self.completed = self.execute_calls == 2
            call_record["returned_status"] = "completed" if self.completed else "progressed"
            return {
                "run_id": self.coordinates["run"],
                "run_status": "succeeded" if self.completed else "running",
                "coordinator_status": call_record["returned_status"],
                "effects_attempted": 1,
                "activity_id": None if self.completed else f"activity-{uuid4().hex}",
            }
        if route_id == "command.graph.advance-current":
            self.case.assertTrue(self.completed, "advanced before completed response")
            self._expect(
                arguments,
                run_id=self.coordinates["run"], plan_id=self.coordinates["plan"],
                claim_generation=self.claim_generation,
                expected_current_graph_id=self.current_graph_id,
                expected_current_realized_projection_id=self.current_projection_id,
                desired_graph_id=self.desired_graph_id,
                desired_realized_projection_id=self.desired_projection_id,
                expected_desired_graph_revision=self.desired_revision,
            )
            self.current_graph_id = str(self.desired_graph_id)
            self.current_projection_id = str(self.desired_projection_id)
            self.current_descriptor = self.pending_descriptor
            return {
                "from_graph_id": arguments["expected_current_graph_id"],
                "to_graph_id": self.current_graph_id,
                "to_realized_projection_id": self.current_projection_id,
                "desired_graph_revision": self.desired_revision,
                "replayed": False,
            }
        if route_id == "read.run-events":
            self._expect(arguments, run_id=self.coordinates["run"])
            cursor = {
                "format_version": 1, "collection": "run-events",
                "scope": {"workspace_id": self.workspace_id, "run_id": self.coordinates["run"]},
                "position": {"ordinal": 1, "item_id": f"event-{self.transition}-1"},
            }
            second = "after" in arguments
            if second:
                self.case.assertEqual(self.transition, 0)
                self.case.assertEqual(arguments["after"], cursor)
            self.case.assertNotIn("cursor", arguments)
            ordinal = 2 if second else 1
            return {
                "workspace_id": self.workspace_id,
                "kind": "run-events",
                "limit": 100,
                "items": [{
                    "event_id": f"event-{self.transition}-{ordinal}", "run_id": self.coordinates["run"],
                    "ordinal": ordinal, "event_type": "run-succeeded" if second else "run-started",
                    "occurred_at": "2026-09-03T12:00:00+00:00", "activity_id": None,
                }],
                "next_cursor": cursor if self.transition == 0 and not second else None,
            }
        if route_id == "read.plan-runs":
            self._expect(arguments, plan_id=self.coordinates["plan"])
            return {
                "workspace_id": self.workspace_id,
                "kind": "plan-runs",
                "limit": 100,
                "items": [{"run_id": self.coordinates["run"], "status": "succeeded"}],
                "next_cursor": None,
            }
        if route_id == "read.observed-state":
            items = []
            for edge in self.current_descriptor["edges"].values():
                router_id = edge["consumer"]["role"]
                router = self.current_descriptor["nodes"][router_id]
                check = next(
                    value for value in router["block_spec"]["verification"]["checks"]
                    if value.get("path") == "/"
                )
                selected = self.current_descriptor["nodes"][edge["provider"]["role"]]
                message = next(
                    binding["value"] for binding in selected["environment_bindings"]
                    if binding["name"] == "HELLO_MESSAGE"
                )
                evidence = {
                    "run_id": self.coordinates["run"],
                    "node_id": router_id, "check_id": check["check_id"],
                    "path": "/", "http_status": 200,
                    "response_bytes": len((message + "\n").encode()),
                    "expected_body_sha256": check["expected_body_sha256"],
                    "body_sha256_matches": True,
                }
                if self.observation_fault == "digest":
                    evidence["expected_body_sha256"] = "0" * 64
                if self.observation_fault == "match":
                    evidence["body_sha256_matches"] = False
                observation = {
                    "observation_id": f"observation-{uuid4().hex}",
                    "observed_at": "2026-09-03T12:00:00+00:00",
                    "subject_id": f"verification:{uuid4().hex}{uuid4().hex}",
                    "graph_id": (
                        f"graph-{uuid4().hex}" if self.observation_fault == "graph"
                        else self.current_graph_id
                    ),
                    "status": "verified", "freshness": "fresh", "stale_reason": None,
                    "payload": {"http_verification": evidence},
                }
                if self.transition in {0, 2}:
                    self.router_observation = observation
                else:
                    self.case.assertIsNotNone(self.router_observation)
                    observation = {**self.router_observation, "freshness": "stale", "stale_reason": "graph-changed"}
                items.append(observation)
            return {
                "workspace_id": self.workspace_id,
                "kind": "observed-state",
                "items": items, "next_cursor": None,
            }
        raise AssertionError(f"unexpected public route: {route_id}")

    def _expect(self, arguments: dict[str, object], **expected: object) -> None:
        self.case.assertEqual(
            {key: arguments.get(key) for key in expected}, expected,
            "public upstream coordinates were not carried forward",
        )

    def _workspace(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "current_graph_id": self.current_graph_id,
            "current_realized_projection_id": self.current_projection_id,
            "desired_graph_id": self.desired_graph_id,
            "desired_realized_projection_id": self.desired_projection_id,
            "desired_graph_revision": self.desired_revision,
        }


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
        occurred_at: str = "2026-08-30T12:00:00Z",
        activity_id: str | None = None,
        payload: dict[str, object] | None = None,
        recovery: dict[str, object] | None = None,
    ) -> dict[str, object]:
        event: dict[str, object] = {
            "event_id": event_id,
            "run_id": run_id,
            "ordinal": ordinal,
            "event_type": event_type,
            "occurred_at": occurred_at,
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
                    occurred_at="2026-08-30T12:00:00.123456Z",
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

        completed = (
            self._execute_result(
                run_status="succeeded",
                coordinator_status="completed",
                effects_attempted=0,
                activity_id=None,
            ),
            self._execute_result(
                run_status="succeeded",
                coordinator_status="completed",
                effects_attempted=1,
                activity_id=None,
            ),
        )
        for index, response in enumerate(completed):
            with self.subTest(completed=index, response=response):
                with patch.object(
                    cpk_server_hosted_activity,
                    "_mcp_tool",
                    return_value=response,
                ) as execute:
                    self._workflow().execute_to_completion(
                        claimed_run=claimed,
                        sync_runtime_networks=False,
                    )
                self.assertEqual(execute.call_count, 1)

        terminal = (
            self._execute_result(
                run_status="failed",
                coordinator_status="failed",
                effects_attempted=1,
            ),
            self._execute_result(
                run_status="failed",
                coordinator_status="unsupported",
                effects_attempted=1,
            ),
            self._execute_result(
                run_status="failed",
                coordinator_status="failed",
                effects_attempted=0,
                activity_id=None,
            ),
            self._execute_result(
                run_status="failed",
                coordinator_status="failed",
                effects_attempted=1,
                activity_id=None,
            ),
            self._execute_result(
                coordinator_status="uncertain",
                effects_attempted=1,
            ),
            self._execute_result(
                coordinator_status="uncertain",
                effects_attempted=0,
            ),
            *(
                self._execute_result(
                    run_status=run_status,
                    coordinator_status="blocked",
                    effects_attempted=0,
                    activity_id=None,
                )
                for run_status in (
                    "paused",
                    "cancelled",
                    "compensating",
                    "compensated",
                    "partially_failed",
                    "uncompensated_failure",
                    "running",
                )
            ),
            self._execute_result(
                run_status="running",
                coordinator_status="blocked",
                effects_attempted=1,
                activity_id=None,
            ),
        )
        for index, response in enumerate(terminal):
            with self.subTest(terminal=index, response=response):
                with (
                    patch.object(
                        cpk_server_hosted_activity,
                        "_mcp_tool",
                        return_value=response,
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

        hostile = (
            self._execute_result(
                run_status="running",
                coordinator_status="completed",
                effects_attempted=0,
                activity_id=None,
            ),
            self._execute_result(
                run_status="succeeded",
                coordinator_status="completed",
                effects_attempted=1,
                activity_id="activity-a",
            ),
            self._execute_result(
                run_status="succeeded",
                coordinator_status="completed",
                effects_attempted=0,
                activity_id="activity-a",
            ),
            self._execute_result(
                run_status="running",
                coordinator_status="failed",
                effects_attempted=1,
            ),
            self._execute_result(
                run_status="failed",
                coordinator_status="failed",
                effects_attempted=0,
            ),
            self._execute_result(
                run_status="failed",
                coordinator_status="unsupported",
                effects_attempted=0,
                activity_id=None,
            ),
            self._execute_result(
                coordinator_status="uncertain",
                effects_attempted=0,
                activity_id=None,
            ),
            self._execute_result(
                run_status="failed",
                coordinator_status="uncertain",
                effects_attempted=1,
            ),
            self._execute_result(
                coordinator_status="blocked",
                effects_attempted=1,
            ),
            self._execute_result(
                run_status="failed",
                coordinator_status="blocked",
                effects_attempted=0,
                activity_id=None,
            ),
            self._execute_result(
                run_status="failed",
                coordinator_status="progressed",
            ),
            self._execute_result(
                coordinator_status="in-flight",
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
        self.assertNotIn(
            "offset",
            inspect.signature(
                cpk_server_hosted_activity.HostedWorkflow.read_plan_detail
            ).parameters,
        )
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
            (
                self._plan_detail_with_plan(
                    created_at="2026-08-30T12:00:00.1Z"
                ),
                self._plan_detail_with_plan(
                    created_at="2026-08-30T12:00:00.1Z"
                ),
            ),
            (
                self._plan_detail_with_plan(
                    created_at="2026-02-30T12:00:00Z"
                ),
                self._plan_detail_with_plan(
                    created_at="2026-02-30T12:00:00Z"
                ),
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
        self.assertNotIn("offset", inspect.signature(reader).parameters)
        self.assertIn("after", inspect.signature(reader).parameters)
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

        after_page = self._run_event_page()
        after_page["items"] = list(after_page["items"])[1:]
        cursor = {
            "format_version": 1,
            "collection": "run-events",
            "scope": {"workspace_id": "workspace-a", "run_id": "run-a"},
            "position": {"ordinal": 1, "item_id": "event-a"},
        }
        encoded_cursor = quote_from_bytes(
            json.dumps(
                cursor,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8"),
            safe="",
        )
        with (
            patch.object(
                cpk_server_hosted_activity,
                "_http",
                return_value=after_page,
            ) as http,
            patch.object(
                cpk_server_hosted_activity,
                "_mcp",
                return_value=after_page,
            ) as mcp,
        ):
            events = self._workflow().read_run_events(
                "run-a",
                limit=100,
                after=cursor,
            )

        self.assertEqual(events, tuple(after_page["items"]))
        self.assertEqual(
            http.call_args.args,
            (
                "http://cpk-server",
                "GET",
                "/workspaces/workspace-a/runs/run-a/events"
                f"?limit=100&after={encoded_cursor}",
            ),
        )
        self.assertNotEqual(http.call_args.kwargs.get("authorize"), False)
        self.assertEqual(
            mcp.call_args.args,
            (
                "http://cpk-server",
                "resources/read",
                "read.run-events",
                {
                    "workspace_id": "workspace-a",
                    "run_id": "run-a",
                    "limit": 100,
                    "after": cursor,
                },
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
        arbitrary_fraction = self._run_event_page()
        arbitrary_fraction["items"] = list(arbitrary_fraction["items"])
        arbitrary_fraction["items"][0] = {
            **arbitrary_fraction["items"][0],
            "occurred_at": "2026-08-30T12:00:00.1Z",
        }
        invalid_date = self._run_event_page()
        invalid_date["items"] = list(invalid_date["items"])
        invalid_date["items"][0] = {
            **invalid_date["items"][0],
            "occurred_at": "2026-02-30T12:00:00Z",
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
            (arbitrary_fraction, arbitrary_fraction),
            (invalid_date, invalid_date),
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

    def test_process_boundary_redacts_uncaught_chained_failures(self) -> None:
        boundary = getattr(cpk_server_hosted_activity, "_sanitized_main", None)
        self.assertIsNotNone(boundary, "hosted workflow lacks sanitized main boundary")
        primary = _PrimaryTransportFailure(
            "raw-response-not-for-output from http://private.example "
            "token-not-for-output credential-not-for-output"
        )
        try:
            raise primary
        except _PrimaryTransportFailure as error:
            try:
                raise RuntimeError("deployment execution failed") from error
            except RuntimeError as wrapped:
                failure = wrapped
        self.assertIs(failure.__cause__, primary)

        def fail() -> int:
            raise failure

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
        ):
            self.assertEqual(boundary(lambda: 0), 0)
            self.assertEqual(boundary(fail), 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "cpk source-live execution failed\n")
        rendered = stdout.getvalue() + stderr.getvalue()
        for forbidden in (
            "raw-response-not-for-output",
            "private.example",
            "token-not-for-output",
            "credential-not-for-output",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_public_graph_convergence_uses_only_authenticated_public_requests(
        self,
    ) -> None:
        try:
            controller = importlib.import_module(
                "scripts.cpk_server_public_graph_convergence"
            )
        except ModuleNotFoundError:
            controller = None
        self.assertIsNotNone(
            controller,
            "public graph convergence controller is not implemented",
        )
        run = getattr(controller, "run_public_graph_convergence", None)
        self.assertTrue(callable(run), "public convergence entrypoint is unavailable")

        colors = ("red", "green", "blue", "gold")
        hello_nodes = tuple(
            {
                "node_id": f"hello-{uuid4().hex[:12]}",
                "name": f"service-{index}",
                "color": color,
                "message": f"Hello from service-{index} in {color}",
            }
            for index, color in enumerate(colors, start=1)
        )
        router_id = f"router-{uuid4().hex[:12]}"
        retained_node_ids = (
            hello_nodes[1]["node_id"],
            hello_nodes[3]["node_id"],
        )

        def invoke(fixture: _PublicConvergenceFixture) -> dict[str, object]:
            return run(
                fixture.invoke,
                servers_repo=Path(__file__).resolve().parents[1],
                workspace_id=fixture.workspace_id,
                router_id=router_id,
                hello_nodes=hello_nodes,
                initial_node_id=hello_nodes[0]["node_id"],
                rewire_node_id=hello_nodes[3]["node_id"],
                retained_node_ids=retained_node_ids,
                authorization=fixture.operator_bearer,
                worker_authorization=fixture.worker_bearer,
                approver_authorization=fixture.approver_bearer,
            )

        fixture = _PublicConvergenceFixture(self)
        result = invoke(fixture)

        self.assertEqual(result["status"], "converged")
        self.assertEqual(result["final_graph_id"], fixture.current_graph_id)
        self.assertEqual(len(result["transitions"]), 6)
        self.assertTrue(
            all(
                call_record["route_id"].startswith(("command.", "read."))
                for call_record in fixture.calls
            )
        )

        prepare_calls = [
            call_record
            for call_record in fixture.calls
            if call_record["route_id"] == "command.deployment.prepare"
        ]
        self.assertEqual(len(prepare_calls), 6)
        descriptors = [
            call_record["arguments"]["desired_graph"]
            for call_record in prepare_calls
        ]
        node_ids = tuple(node["node_id"] for node in hello_nodes)
        expected_node_sets = (
            {node_ids[0], router_id},
            {*node_ids, router_id},
            {*node_ids, router_id},
            {*retained_node_ids, router_id},
            {*retained_node_ids, router_id},
            set(),
        )
        selected_ids = (
            node_ids[0],
            node_ids[0],
            node_ids[3],
            node_ids[3],
            node_ids[3],
        )
        messages = {node["node_id"]: node["message"] for node in hello_nodes}
        for index, descriptor in enumerate(descriptors):
            with self.subTest(transition=index):
                self.assertEqual(set(descriptor["nodes"]), expected_node_sets[index])
                if index == 5:
                    self.assertEqual(descriptor["edges"], {})
                    continue
                edge = next(iter(descriptor["edges"].values()))
                self.assertEqual(edge["provider"]["role"], selected_ids[index])
                self.assertEqual(edge["consumer"]["role"], router_id)
                router = descriptor["nodes"][router_id]
                body_check = next(
                    check
                    for check in router["block_spec"]["verification"]["checks"]
                    if check.get("path") == "/"
                )
                self.assertEqual(
                    body_check["expected_body_sha256"],
                    sha256((messages[selected_ids[index]] + "\n").encode()).hexdigest(),
                )
                for node_id in expected_node_sets[index] - {router_id}:
                    bindings = descriptor["nodes"][node_id]["environment_bindings"]
                    hello_message = next(
                        binding["value"]
                        for binding in bindings
                        if binding["name"] == "HELLO_MESSAGE"
                    )
                    self.assertEqual(hello_message, messages[node_id])

        self.assertEqual(descriptors[3], descriptors[4], "no-op graph drifted")
        no_op_commands = [
            call_record["route_id"]
            for call_record in fixture.calls
            if call_record["transition"] == 4
            and call_record["route_id"].startswith("command.")
        ]
        self.assertEqual(no_op_commands, ["command.deployment.prepare"])
        destructive_approvals = [
            call_record
            for call_record in fixture.calls
            if call_record["route_id"] == "command.approval.decide"
            and call_record["transition"] in {3, 5}
        ]
        self.assertEqual(len(destructive_approvals), 2)
        self.assertTrue(
            all(
                call_record["authorization"] == fixture.approver_bearer
                for call_record in destructive_approvals
            )
        )
        self.assertNotEqual(fixture.operator_bearer, fixture.approver_bearer)
        self.assertEqual(len(result["transitions"][0]["events"]), 2)
        self.assertEqual([event["ordinal"] for event in result["transitions"][0]["events"]], [1, 2])
        for fresh, unchanged in ((0, 1), (2, 3)):
            original = result["transitions"][fresh]["response"]
            historical = result["transitions"][unchanged]["response"]
            self.assertEqual(original["basis"], "current-run")
            self.assertEqual(historical["basis"], "historical-unchanged-router")
            self.assertEqual(historical["freshness"], "stale")
            for key in ("observation_id", "graph_id", "run_id"):
                self.assertEqual(historical[key], original[key])
            self.assertNotEqual(historical["graph_id"], result["transitions"][unchanged]["graph_id"])
        for transition in (0, 1, 2, 3, 5):
            with self.subTest(completed_transition=transition):
                calls = [row for row in fixture.calls if row["transition"] == transition]
                executions = [
                    row for row in calls if row["route_id"] == "command.deployment.execute"
                ]
                self.assertEqual(
                    [row["returned_status"] for row in executions],
                    ["progressed", "completed"],
                )
                self.assertEqual(
                    len({row["arguments"]["idempotency_key"] for row in executions}), 2,
                )
                advance = next(
                    row for row in calls if row["route_id"] == "command.graph.advance-current"
                )
                self.assertGreater(calls.index(advance), calls.index(executions[-1]))
                self.assertTrue(any(
                    row["route_id"] == "read.current-graph"
                    for row in calls[calls.index(advance) + 1:]
                ))
                self.assertTrue(any(row["route_id"] == "read.run-events" for row in calls))
                retained = result["transitions"][transition]
                self.assertIn("activities", retained["plan"])
                self.assertNotEqual(retained["approval"]["requested_by"], retained["approval"]["decision"]["actor_id"])
                self.assertTrue(retained["events"])
                self.assertEqual(retained["outcomes"][-1]["coordinator_status"], "completed")
                if transition != 5:
                    self.assertTrue(any(row["route_id"] == "read.observed-state" for row in calls))

        for fault in ("graph", "digest", "match"):
            with self.subTest(observation=fault):
                mismatched = _PublicConvergenceFixture(self, observation_fault=fault)
                rejected = invoke(mismatched)
                self.assertEqual(rejected["status"], "attention-required")
                self.assertTrue(any(
                    row["route_id"] == "read.observed-state" for row in mismatched.calls
                ))
                self.assertEqual(sum(
                    row["route_id"] == "command.deployment.prepare" for row in mismatched.calls
                ), 1)

        attention = _PublicConvergenceFixture(self, attention_status="uncertain")
        stopped = invoke(attention)
        self.assertEqual(stopped["status"], "attention-required")
        self.assertEqual(stopped["coordinator_status"], "uncertain")
        self.assertEqual(
            sum(
                call_record["route_id"] == "command.deployment.execute"
                for call_record in attention.calls
            ),
            1,
        )
        self.assertFalse(
            any(
                call_record["route_id"] == "command.graph.advance-current"
                for call_record in attention.calls
            )
        )
        self.assertEqual(
            sum(
                call_record["route_id"] == "command.deployment.prepare"
                for call_record in attention.calls
            ),
            1,
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
