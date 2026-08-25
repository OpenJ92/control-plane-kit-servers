from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, field
import importlib
import importlib.util
import inspect
import json
from typing import Any
import unittest

from control_plane_kit_core.topology import DeploymentGraph


MODULE_NAME = "scripts.cpk_server_candidate_live_acceptance"
HELLO_IMAGE = (
    "ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:"
    "e2288b23844b1f0b7526d2798cbc1eaf6e9f536399173a043e7957f0e7730cbf"
)
ROUTER_IMAGE = (
    "ghcr.io/openj92/control-plane-kit-servers/http-active-router@sha256:"
    "a58938fdc5c37bfda1b2b0dbd95fc0bf3ba7391f5ce3b8fdfb3956dccf0a01c8"
)
HELLO_RESPONSE = b"Hello, world!\n"
BLUE_RESPONSE = b"Hello from blue\n"
GREEN_RESPONSE = b"Hello from green\n"
BLUE_GREEN_STAGES = (
    "blue-realization",
    "green-preparation",
    "green-cutover",
    "rollback-blue",
    "final-green",
    "retire-blue",
    "teardown",
)


@dataclass
class RecordingWorkflow:
    ledger: list[tuple[str, Any]] = field(default_factory=list)
    current_graph_id: str = "graph-predecessor"
    active_stage: str = ""
    activity: tuple[str, ...] = ()
    expected_predecessors: list[str | None] = field(default_factory=list)
    failure_stage: str | None = None
    failure: BaseException = field(
        default_factory=lambda: RuntimeError("protected-workflow-failure")
    )
    hostile_projection: Any = None
    approval_extra: tuple[str, Any] | None = None

    def start_session(self, title: str) -> str:
        self.active_stage = title
        self.ledger.append(("start-session", title))
        return f"session-{title}"

    def set_desired_graph(self, **kwargs: Any) -> str:
        self.expected_predecessors.append(kwargs["expected_desired_graph_id"])
        self.ledger.append(("set-desired", self.active_stage))
        return f"graph-{self.active_stage}"

    def plan_transition(self, **_kwargs: Any) -> str:
        self.ledger.append(("plan", self.active_stage))
        return f"plan-{self.active_stage}"

    def request_approval(self, **_kwargs: Any) -> dict[str, object]:
        self.ledger.append(("request-approval", self.active_stage))
        approval = {
            "action_id": f"action-{self.active_stage}",
            "action_ordinal": 1,
            "destructive": True,
            "max_risk": "critical",
            "plan_id": f"plan-{self.active_stage}",
            "replayed": False,
            "request_id": f"approval-{self.active_stage}",
            "requested_at": "2026-08-25T12:00:00Z",
            "requested_by": "operator-a",
            "required_scope": "plan:approve-destructive",
            "session_id": f"session-{self.active_stage}",
            "state": "pending",
        }
        if self.approval_extra is not None:
            approval[self.approval_extra[0]] = self.approval_extra[1]
        return approval

    def assert_approval_visible(self, approval_id: str, plan_id: str) -> None:
        self.ledger.append(("approval-visible", self.active_stage))

    def approve(self, **_kwargs: Any) -> None:
        self.ledger.append(("approve", self.active_stage))

    def admit(self, **_kwargs: Any) -> str:
        self.ledger.append(("admit", self.active_stage))
        return f"request-{self.active_stage}"

    def claim(self, **_kwargs: Any) -> str:
        self.ledger.append(("claim", self.active_stage))
        return f"run-{self.active_stage}"

    def start_run(self, **_kwargs: Any) -> None:
        self.ledger.append(("start-run", self.active_stage))

    def execute_to_completion(
        self,
        run_id: str,
        *,
        sync_runtime_networks: bool,
    ) -> None:
        self.ledger.append(
            ("execute", (self.active_stage, sync_runtime_networks))
        )
        if self.failure_stage == self.active_stage:
            raise self.failure
        self.activity = (
            *self.activity,
            f"{self.active_stage}-effect-attempt-complete",
        )

    def read_current_graph_http(self) -> dict[str, Any]:
        self.ledger.append(("read-http", self.active_stage))
        if self.hostile_projection is not None:
            return self.hostile_projection
        return {"graph_id": self.current_graph_id, "activity": self.activity}

    def read_current_graph_mcp(self) -> dict[str, Any]:
        self.ledger.append(("read-mcp", self.active_stage))
        return {"graph_id": self.current_graph_id, "activity": self.activity}

    def advance_current_graph(self, **kwargs: Any) -> str:
        self.current_graph_id = kwargs["desired_graph_id"]
        self.ledger.append(("advance", self.active_stage))
        return self.current_graph_id

    def read_activity_http(self) -> dict[str, Any]:
        self.ledger.append(("history-http", self.activity))
        return {"events": self.activity}

    def read_activity_mcp(self) -> dict[str, Any]:
        self.ledger.append(("history-mcp", self.activity))
        return {"events": self.activity}


@dataclass
class RecordingProbeEffects:
    responses: list[bytes]
    ledger: list[tuple[str, Any]] = field(default_factory=list)
    probe_id: str | None = None

    def probe_runtime_node(
        self,
        *,
        node_id: str,
        expected_image_reference: str,
        labelled: bool,
        attach_runtime_network: bool,
    ) -> dict[str, Any]:
        if self.probe_id is None:
            self.probe_id = "candidate-probe"
            self.ledger.append(("probe-created", self.probe_id))
        response = self.responses.pop(0)
        self.ledger.append(("probe", node_id))
        return {
            "response": response,
            "container_id": self.probe_id,
            "request_origin": "inside-probe",
            "target_image_id": "sha256:" + "7" * 64,
            "target_image_reference": expected_image_reference,
        }

    def remove_probe(self) -> None:
        if self.probe_id is not None:
            self.ledger.append(("remove-probe", self.probe_id))
            self.probe_id = None


class CandidateLiveAcceptanceTests(unittest.TestCase):
    def _module(self) -> Any:
        spec = importlib.util.find_spec(MODULE_NAME)
        self.assertIsNotNone(
            spec,
            "typed candidate transition boundary is not implemented",
        )
        if spec is None:
            return None
        return importlib.import_module(MODULE_NAME)

    def _probe(self, live: Any, response: bytes = HELLO_RESPONSE) -> Any:
        return live.CandidateProbeSpec(
            node_id="hello",
            image_reference=HELLO_IMAGE,
            expected_response=response,
        )

    def _graph_readback(self) -> dict[str, Any]:
        return {
            "assigned": True,
            "authored_graph_id": "graph-authored",
            "graph_descriptor": {
                "edges": {},
                "name": "candidate-topology-1723",
                "nodes": {},
                "public_ingresses": [],
                "runtimes": {},
            },
            "graph_id": "graph-predecessor",
            "graph_name": "candidate-topology-1723",
            "pointer": "current",
            "realized_projection_id": "projection-" + "1" * 64,
            "version": 1,
        }

    def _activity_history(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "actor_id": "operator-a",
                    "closed_at": None,
                    "created_at": "2026-08-25T12:00:00Z",
                    "metadata": {},
                    "session_id": "session-hello",
                    "status": "open",
                    "title": "hello",
                    "workspace_id": "candidate-topology-1723",
                }
            ],
            "kind": "activity-sessions",
            "limit": 50,
            "next_cursor": None,
            "workspace_id": "candidate-topology-1723",
        }

    def _graph_readback_with_node(self) -> dict[str, Any]:
        document = self._graph_readback()
        document["graph_descriptor"] = {
            "edges": {},
            "name": "candidate-topology-1723",
            "nodes": {
                "hello": {
                    "block_family": "application",
                    "block_spec": {
                        "capabilities": ["health-checkable"],
                        "display_name": "hello-server",
                        "health_path": None,
                        "metadata": {},
                        "role_id": "hello",
                        "variant": "block",
                        "verification": {
                            "checks": [
                                {
                                    "check_id": "live",
                                    "expected_statuses": [200],
                                    "kind": "http",
                                    "path": "/health/live",
                                    "policy": {
                                        "interval_seconds": 1.0,
                                        "maximum_attempts": 5,
                                        "maximum_evidence_bytes": 16384,
                                        "timeout_seconds": 5.0,
                                    },
                                    "provider_socket": "internal",
                                }
                            ]
                        },
                    },
                    "configuration_artifacts": [],
                    "endpoints": {
                        "internal": {
                            "address": "<redacted>",
                            "protocol": {
                                "application": "http",
                                "transport": "tcp",
                            },
                            "scope": "private",
                        }
                    },
                    "environment_bindings": [
                        {
                            "kind": "public-static",
                            "name": "HELLO_MESSAGE",
                            "value": "<redacted>",
                        }
                    ],
                    "kind": "oci-container",
                    "lifecycle": {
                        "compute": "ephemeral",
                        "data": [],
                        "ownership": "owned",
                    },
                    "metadata": {
                        "block_family": "ApplicationBlock",
                        "capabilities": [
                            {
                                "description": "Node exposes health state.",
                                "label": "Health",
                                "name": "health-checkable",
                                "route_set": "common-status",
                            }
                        ],
                        "display_name": "hello-server",
                        "oci_image": HELLO_IMAGE,
                        "product_descriptor_digest": "1" * 64,
                        "product_identity": "control-plane-kit/hello-server/1",
                    },
                    "node_id": "hello",
                    "providers": {
                        "internal": {
                            "protocol": {
                                "application": "http",
                                "transport": "tcp",
                            }
                        }
                    },
                    "requirements": {},
                    "runtime_id": "docker",
                    "secret_deliveries": "<redacted>",
                }
            },
            "public_ingresses": [],
            "runtimes": {
                "docker": {
                    "authority_ref": None,
                    "children": ["hello"],
                    "kind": "docker",
                    "lifecycle": {
                        "compute": "ephemeral",
                        "data": [],
                        "ownership": "owned",
                    },
                    "metadata": {
                        "network_name": "candidate-topology-1723-docker",
                    },
                }
            },
        }
        return document

    def test_graph_readback_projection_is_closed_and_preserves_exact_document(self) -> None:
        live = self._module()
        if live is None:
            return
        with self.subTest(boundary="closed-graph-readback-type"):
            self.assertTrue(
                hasattr(live, "CandidateGraphReadbackProjection"),
                "graph readback requires its own closed projection",
            )
        projection_type = getattr(live, "CandidateGraphReadbackProjection", None)
        if projection_type is None:
            projection_type = live.CandidatePublicProjection
        document = self._graph_readback()
        self.assertEqual(projection_type.admit(document).to_document(), document)

        hostile_documents = (
            {**document, "scenario_payload": {"arbitrary": True}},
            {**document, "provider_message": "failed"},
            {**document, "arbitrary": {"object": {"accepted": True}}},
            {
                **document,
                "graph_descriptor": {
                    **document["graph_descriptor"],
                    "scenario_payload": {},
                },
            },
            {
                **document,
                "graph_descriptor": {
                    **document["graph_descriptor"],
                    "authorization": "redacted",
                },
            },
        )
        for hostile in hostile_documents:
            with self.subTest(hostile=hostile):
                workflow = RecordingWorkflow()
                with self.assertRaises(live.CandidateTopologyError):
                    projection_type.admit(hostile)
                self.assertEqual(workflow.ledger, [])

    def test_graph_readback_projection_admits_only_schema_owned_coordinates(self) -> None:
        live = self._module()
        if live is None:
            return
        projection_type = live.CandidateGraphReadbackProjection
        document = self._graph_readback_with_node()
        with self.subTest(boundary="schema-owned-http-path-and-oci-coordinate"):
            try:
                projection = projection_type.admit(document)
            except live.CandidateTopologyError:
                self.fail("closed graph projection rejected schema-owned coordinates")
            self.assertEqual(projection.to_document(), document)

        hostile = json.loads(json.dumps(document))
        hostile["graph_descriptor"]["nodes"]["hello"]["block_spec"][
            "verification"
        ]["checks"][0]["path"] = "/token=opaque-material"
        with self.subTest(boundary="http-path-rejects-protected-material"):
            with self.assertRaises(live.CandidateTopologyError):
                projection_type.admit(hostile)

    def test_activity_history_projection_rejects_sensitive_surface_before_activity(self) -> None:
        live = self._module()
        if live is None:
            return
        with self.subTest(boundary="closed-activity-history-type"):
            self.assertTrue(
                hasattr(live, "CandidateActivityHistoryProjection"),
                "activity history requires its own closed projection",
            )
        projection_type = getattr(live, "CandidateActivityHistoryProjection", None)
        if projection_type is None:
            projection_type = live.CandidatePublicProjection
        document = self._activity_history()
        self.assertEqual(projection_type.admit(document).to_document(), document)

        hostile_values = (
            "worker.internal.example",
            "2001:db8::1",
            "/var/lib/control-plane-kit/state.json",
            "/var/run/docker.sock",
            "api_key=opaque-material",
            "dockerd build session failed",
        )
        for hostile in hostile_values:
            with self.subTest(hostile=hostile):
                candidate = json.loads(json.dumps(document))
                candidate["items"][0]["title"] = hostile
                workflow = RecordingWorkflow()
                with self.assertRaises(live.CandidateTopologyError):
                    projection_type.admit(candidate)
                self.assertEqual(workflow.ledger, [])

        for key in ("scenario_payload", "provider_message", "authorization"):
            with self.subTest(key=key):
                candidate = json.loads(json.dumps(document))
                candidate["items"][0][key] = {"arbitrary": True}
                workflow = RecordingWorkflow()
                with self.assertRaises(live.CandidateTopologyError):
                    projection_type.admit(candidate)
                self.assertEqual(workflow.ledger, [])

    def test_approval_projection_is_closed_before_decision_activity(self) -> None:
        live = self._module()
        if live is None:
            return
        approval_keys = frozenset(
            (
                "action_id",
                "action_ordinal",
                "destructive",
                "max_risk",
                "plan_id",
                "replayed",
                "request_id",
                "requested_at",
                "requested_by",
                "required_scope",
                "session_id",
                "state",
            )
        )
        with self.subTest(boundary="closed-approval-type"):
            self.assertTrue(
                hasattr(live, "CandidateApprovalProjection"),
                "approval response requires a closed projection",
            )
        approval = {
            "action_id": "action-hello",
            "action_ordinal": 1,
            "destructive": True,
            "max_risk": "critical",
            "plan_id": "plan-hello",
            "replayed": False,
            "request_id": "approval-hello",
            "requested_at": "2026-08-25T12:00:00Z",
            "requested_by": "operator-a",
            "required_scope": "plan:approve-destructive",
            "session_id": "session-hello",
            "state": "pending",
        }
        projection = None
        if hasattr(live, "CandidateApprovalProjection"):
            with self.subTest(boundary="exact-live-approval-document"):
                try:
                    projection = live.CandidateApprovalProjection.admit(
                        approval,
                        expected_plan_id="plan-hello",
                    )
                except live.CandidateTopologyError:
                    self.fail("closed approval projection rejected the live document")
        if projection is not None:
            self.assertEqual(projection.to_document(), approval)
            self.assertEqual(frozenset(projection.to_document()), approval_keys)
            self.assertEqual(projection["request_id"], "approval-hello")
        admitted_approval = {**approval, "max_risk": "high"}

        for max_risk in (
            "informational",
            "low",
            "medium",
            "high",
            "critical",
        ):
            with self.subTest(accepted_max_risk=max_risk):
                candidate = {**approval, "max_risk": max_risk}
                try:
                    admitted = live.CandidateApprovalProjection.admit(
                        candidate,
                        expected_plan_id="plan-hello",
                    )
                except live.CandidateTopologyError:
                    self.fail(f"closed approval rejected Core risk {max_risk}")
                self.assertEqual(admitted.to_document(), candidate)

        for destructive, required_scope in (
            (False, "plan:approve"),
            (True, "plan:approve-destructive"),
        ):
            for replayed in (False, True):
                with self.subTest(
                    destructive=destructive,
                    required_scope=required_scope,
                    replayed=replayed,
                ):
                    candidate = {
                        **admitted_approval,
                        "destructive": destructive,
                        "replayed": replayed,
                        "required_scope": required_scope,
                    }
                    self.assertEqual(
                        live.CandidateApprovalProjection.admit(
                            candidate,
                            expected_plan_id="plan-hello",
                        ).to_document(),
                        candidate,
                    )

        rejected_values = (
            ("action_id", ""),
            ("action_ordinal", 0),
            ("action_ordinal", -1),
            ("action_ordinal", True),
            ("destructive", 1),
            ("max_risk", "moderate"),
            ("max_risk", "destructive"),
            ("max_risk", "CRITICAL"),
            ("plan_id", "plan-other"),
            ("replayed", 0),
            ("request_id", "/tmp/request"),
            ("requested_at", "2026-08-25"),
            ("requested_by", "operator.internal.example"),
            ("required_scope", "plan:request"),
            ("required_scope", "plan:execute"),
            ("session_id", "2001:db8::1"),
            ("state", "approved"),
            ("state", "rejected"),
        )
        for field_name, rejected in rejected_values:
            with self.subTest(rejected_field=field_name, rejected_value=rejected):
                with self.assertRaises(live.CandidateTopologyError):
                    live.CandidateApprovalProjection.admit(
                        {**admitted_approval, field_name: rejected},
                        expected_plan_id="plan-hello",
                    )

        for destructive, required_scope in (
            (False, "plan:approve-destructive"),
            (True, "plan:approve"),
        ):
            with self.subTest(
                rejected_destructive=destructive,
                rejected_required_scope=required_scope,
            ):
                with self.assertRaises(live.CandidateTopologyError):
                    live.CandidateApprovalProjection.admit(
                        {
                            **admitted_approval,
                            "destructive": destructive,
                            "required_scope": required_scope,
                        },
                        expected_plan_id="plan-hello",
                    )

        for missing in sorted(approval_keys):
            with self.subTest(missing=missing):
                candidate = dict(approval)
                del candidate[missing]
                with self.assertRaises(live.CandidateTopologyError):
                    live.CandidateApprovalProjection.admit(
                        candidate,
                        expected_plan_id="plan-hello",
                    )

        for extra in ("provider_message", "scenario_payload", "authorization"):
            with self.subTest(extra=extra):
                workflow = RecordingWorkflow()
                with self.assertRaises(live.CandidateTopologyError):
                    live.CandidateApprovalProjection.admit(
                        {**approval, extra: "opaque"},
                        expected_plan_id="plan-hello",
                    )
                self.assertNotIn(("approve", "hello"), workflow.ledger)

    def test_workflow_port_has_explicit_candidate_owned_fencing_signatures(self) -> None:
        live = self._module()
        if live is None:
            return
        expected_parameters = {
            "set_desired_graph": (
                "self",
                "session_id",
                "graph",
                "title",
                "expected_desired_graph_id",
            ),
            "plan_transition": (
                "self",
                "session_id",
                "title",
                "current_graph_id",
                "desired_graph_id",
            ),
            "request_approval": ("self", "session_id", "title", "plan_id"),
            "approve": ("self", "session_id", "title", "approval"),
            "admit": (
                "self",
                "session_id",
                "title",
                "plan_id",
                "approval_id",
            ),
            "claim": ("self", "title", "request_id"),
            "start_run": ("self", "title", "run_id"),
            "advance_current_graph": (
                "self",
                "title",
                "run_id",
                "plan_id",
                "current_graph_id",
                "desired_graph_id",
            ),
        }
        for name, expected in expected_parameters.items():
            with self.subTest(name=name):
                signature = inspect.signature(
                    getattr(live.CandidateWorkflowPort, name)
                )
                self.assertEqual(tuple(signature.parameters), expected)
                self.assertNotIn(
                    inspect.Parameter.VAR_KEYWORD,
                    tuple(
                        parameter.kind
                        for parameter in signature.parameters.values()
                    ),
                )

    def test_program_is_closed_immutable_and_validated_before_activity(self) -> None:
        live = self._module()
        if live is None:
            return
        graph = DeploymentGraph("candidate-topology-1723")
        probe = self._probe(live)
        transition = live.CandidateTransitionSpec("hello", graph, probe)
        program = live.CandidateTransitionProgram(
            (
                transition,
                live.CandidateTransitionSpec("teardown", graph, None),
            )
        )

        with self.assertRaises(FrozenInstanceError):
            transition.stage = "changed"
        with self.assertRaises(FrozenInstanceError):
            program.transitions = ()
        with self.assertRaises(TypeError):
            live.CandidateTransitionSpec(
                stage="hello",
                graph=graph,
                probe=probe,
                scenario_payload={"arbitrary": True},
            )

        invalid_programs = (
            [transition],
            (transition, transition),
            (
                live.CandidateTransitionSpec("hello", object(), probe),
                live.CandidateTransitionSpec("teardown", graph, None),
            ),
            (
                live.CandidateTransitionSpec("teardown", graph, None),
                transition,
            ),
        )
        for candidate in invalid_programs:
            with self.subTest(candidate=repr(candidate)):
                with self.assertRaises(live.CandidateTransitionProgramError):
                    live.CandidateTransitionProgram(candidate)

        invalid_probes = (
            {"node_id": "Hello", "image_reference": HELLO_IMAGE, "expected_response": HELLO_RESPONSE},
            {"node_id": "hello", "image_reference": "hello:latest", "expected_response": HELLO_RESPONSE},
            {"node_id": "hello", "image_reference": HELLO_IMAGE, "expected_response": bytearray(HELLO_RESPONSE)},
        )
        for values in invalid_probes:
            with self.subTest(values=values):
                with self.assertRaises(live.CandidateTransitionProgramError):
                    live.CandidateProbeSpec(**values)

    def test_two_step_single_hello_preserves_fencing_probe_and_history(self) -> None:
        live = self._module()
        if live is None:
            return
        workflow = RecordingWorkflow()
        effects = RecordingProbeEffects([HELLO_RESPONSE])
        program = live.CandidateTransitionProgram(
            (
                live.CandidateTransitionSpec(
                    "hello",
                    DeploymentGraph("hello"),
                    self._probe(live),
                ),
                live.CandidateTransitionSpec(
                    "empty-successor",
                    DeploymentGraph("empty"),
                    None,
                ),
            )
        )

        evidence = live.execute_candidate_transitions(
            workflow,
            effects,
            program,
            current_graph_id="graph-predecessor",
        )
        document = evidence.to_document()

        self.assertEqual(
            tuple(row["stage"] for row in document["transitions"]),
            ("hello", "empty-successor"),
        )
        self.assertEqual(
            workflow.expected_predecessors,
            [None, "graph-hello"],
        )
        self.assertEqual(
            document["transitions"][0]["probe"]["response"],
            HELLO_RESPONSE.decode("ascii"),
        )
        self.assertIsNone(document["transitions"][1]["probe"])
        self.assertEqual(document["history_http"], document["history_mcp"])
        self.assertLess(
            effects.ledger.index(("probe", "hello")),
            effects.ledger.index(("remove-probe", "candidate-probe")),
        )
        self.assertEqual(
            evidence.canonical_json(),
            json.dumps(
                document,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )

    def test_seven_step_blue_green_preserves_rollback_and_one_probe(self) -> None:
        live = self._module()
        if live is None:
            return
        responses = (
            BLUE_RESPONSE,
            BLUE_RESPONSE,
            GREEN_RESPONSE,
            BLUE_RESPONSE,
            GREEN_RESPONSE,
            GREEN_RESPONSE,
        )
        workflow = RecordingWorkflow()
        effects = RecordingProbeEffects(list(responses))
        transitions = tuple(
            live.CandidateTransitionSpec(
                stage,
                DeploymentGraph(stage),
                (
                    live.CandidateProbeSpec(
                        node_id="router",
                        image_reference=ROUTER_IMAGE,
                        expected_response=responses[index],
                    )
                    if stage != "teardown"
                    else None
                ),
            )
            for index, stage in enumerate(BLUE_GREEN_STAGES)
        )

        evidence = live.execute_candidate_transitions(
            workflow,
            effects,
            live.CandidateTransitionProgram(transitions),
            current_graph_id="graph-predecessor",
        )
        document = evidence.to_document()

        self.assertEqual(
            tuple(row["stage"] for row in document["transitions"]),
            BLUE_GREEN_STAGES,
        )
        self.assertEqual(
            tuple(
                row["probe"]["response"]
                for row in document["transitions"]
                if row["probe"] is not None
            ),
            tuple(response.decode("ascii") for response in responses),
        )
        self.assertEqual(
            effects.ledger.count(("probe-created", "candidate-probe")),
            1,
        )
        self.assertEqual(
            effects.ledger.count(("remove-probe", "candidate-probe")),
            1,
        )
        self.assertEqual(document["history_http"], document["history_mcp"])
        self.assertIn("rollback-blue-effect-attempt-complete", json.dumps(document))

    def test_failure_preserves_identity_stage_and_external_cleanup_authority(self) -> None:
        live = self._module()
        if live is None:
            return
        failure = RuntimeError("protected-green-preparation-failure")
        workflow = RecordingWorkflow(
            failure_stage="green-preparation",
            failure=failure,
        )
        effects = RecordingProbeEffects([BLUE_RESPONSE])
        program = live.CandidateTransitionProgram(
            (
                live.CandidateTransitionSpec(
                    "blue-realization",
                    DeploymentGraph("blue"),
                    live.CandidateProbeSpec(
                        "router",
                        ROUTER_IMAGE,
                        BLUE_RESPONSE,
                    ),
                ),
                live.CandidateTransitionSpec(
                    "green-preparation",
                    DeploymentGraph("prepared"),
                    live.CandidateProbeSpec(
                        "router",
                        ROUTER_IMAGE,
                        BLUE_RESPONSE,
                    ),
                ),
                live.CandidateTransitionSpec(
                    "teardown",
                    DeploymentGraph("empty"),
                    None,
                ),
            )
        )

        escaped = None
        try:
            live.execute_candidate_transitions(
                workflow,
                effects,
                program,
                current_graph_id="graph-predecessor",
            )
        except BaseException as error:
            escaped = error

        self.assertIs(escaped, failure)
        self.assertEqual(
            getattr(escaped, "candidate_transition_stage", None),
            "green-preparation",
        )
        self.assertNotIn(("start-session", "teardown"), workflow.ledger)
        self.assertFalse(any(name.startswith("history-") for name, _ in workflow.ledger))
        self.assertFalse(any(name == "cleanup" for name, _ in effects.ledger))

    def test_typed_serialization_rejects_protected_or_provider_material(self) -> None:
        live = self._module()
        if live is None:
            return
        protected_values = (
            "password=not-for-output",
            "secret://runtime/authority",
            "https://credential@example.invalid/path",
            "127.0.0.1:8080",
            "/var/run/docker.sock",
            "Authorization: Bearer protected",
            "raw provider exception output",
        )
        for protected in protected_values:
            with self.subTest(protected=protected):
                workflow = RecordingWorkflow(
                    hostile_projection={"graph_id": "graph-predecessor", "value": protected}
                )
                effects = RecordingProbeEffects([HELLO_RESPONSE])
                program = live.CandidateTransitionProgram(
                    (
                        live.CandidateTransitionSpec(
                            "hello",
                            DeploymentGraph("hello"),
                            self._probe(live),
                        ),
                        live.CandidateTransitionSpec(
                            "teardown",
                            DeploymentGraph("empty"),
                            None,
                        ),
                    )
                )
                with self.assertRaisesRegex(
                    live.CandidateTopologyError,
                    "candidate topology workflow failed",
                ) as raised:
                    live.execute_candidate_transitions(
                        workflow,
                        effects,
                        program,
                        current_graph_id="graph-predecessor",
                    )
                self.assertEqual(
                    getattr(raised.exception, "candidate_transition_stage", None),
                    "hello",
                )
                self.assertNotIn(protected, repr(effects.ledger))


if __name__ == "__main__":
    unittest.main()
