from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, field
import importlib
import importlib.util
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

    def request_approval(self, **_kwargs: Any) -> dict[str, str]:
        self.ledger.append(("request-approval", self.active_stage))
        return {"request_id": f"approval-{self.active_stage}"}

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
