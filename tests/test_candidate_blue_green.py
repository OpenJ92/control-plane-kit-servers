from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import importlib
import json
from pathlib import Path
from typing import Any, Callable
import unittest

from control_plane_kit_core.topology import DeploymentGraph

from candidate_topology_fixture import (
    CANDIDATE_IMAGE_ID,
    FOREIGN_INVENTORY,
    FOREIGN_RESOURCE_CANARY,
    exact_assembly,
    exact_inspection,
)


ROOT = Path(__file__).resolve().parents[1]
BLUE_GREEN_SCENARIO = "candidate.topology.blue-green.v1"
BLUE_RESPONSE = b"Hello from blue\n"
GREEN_RESPONSE = b"Hello from green\n"
ROUTER_IMAGE = (
    "ghcr.io/openj92/control-plane-kit-servers/http-active-router@sha256:"
    "a58938fdc5c37bfda1b2b0dbd95fc0bf3ba7391f5ce3b8fdfb3956dccf0a01c8"
)
ROUTER_DESCRIPTOR_SHA256 = (
    "2e4c1ca0e0f59844c06bc754b41ca82a31826d3e12760912f49de1f15bd1f18d"
)
TRANSITIONS = (
    "blue-realization",
    "green-preparation",
    "green-cutover",
    "rollback-blue",
    "final-green",
    "retire-blue",
    "teardown",
)
RESPONSES = (
    ("blue-realization", BLUE_RESPONSE),
    ("green-preparation", BLUE_RESPONSE),
    ("green-cutover", GREEN_RESPONSE),
    ("rollback-blue", BLUE_RESPONSE),
    ("final-green", GREEN_RESPONSE),
    ("retire-blue", GREEN_RESPONSE),
)


def _edge_roles(graph: DeploymentGraph) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        sorted(
            (
                edge.provider_role,
                edge.provider_socket,
                edge.consumer_role,
                edge.requirement_socket,
            )
            for edge in graph.edges.values()
        )
    )


@dataclass
class RecordingBlueGreenWorkflow:
    ledger: list[tuple[str, Any]] = field(default_factory=list)
    fail_at: str | None = None
    current_graph_id: str = "graph-predecessor"
    active_transition: str = ""
    activity: tuple[str, ...] = ()
    graphs: dict[str, DeploymentGraph] = field(default_factory=dict)
    expected_predecessors: dict[str, str | None] = field(default_factory=dict)
    failure: BaseException = field(
        default_factory=lambda: RuntimeError(
            "protected-green-preparation-failure"
        )
    )

    def start_session(self, title: str) -> str:
        self.active_transition = title
        self.ledger.append(("start-session", title))
        return f"session-{title}"

    def set_desired_graph(self, **kwargs: Any) -> str:
        title = self.active_transition
        self.graphs[title] = kwargs["graph"]
        self.expected_predecessors[title] = kwargs["expected_desired_graph_id"]
        self.ledger.append(("set-desired", title))
        return f"graph-{title}"

    def plan_transition(self, **kwargs: Any) -> str:
        self.ledger.append(("plan", self.active_transition))
        return f"plan-{self.active_transition}"

    def request_approval(self, **kwargs: Any) -> dict[str, object]:
        self.ledger.append(("request-approval", self.active_transition))
        return {
            "action_id": f"action-{self.active_transition}",
            "action_ordinal": 1,
            "destructive": True,
            "max_risk": "critical",
            "plan_id": f"plan-{self.active_transition}",
            "replayed": False,
            "request_id": f"approval-{self.active_transition}",
            "requested_at": "2026-08-25T12:00:00Z",
            "requested_by": "operator-a",
            "required_scope": "plan:approve-destructive",
            "session_id": f"session-{self.active_transition}",
            "state": "pending",
        }

    def assert_approval_visible(self, approval_id: str, plan_id: str) -> None:
        self.ledger.append(("approval-visible", self.active_transition))

    def approve(self, **kwargs: Any) -> None:
        self.ledger.append(("approve", self.active_transition))

    def admit(self, **kwargs: Any) -> str:
        self.ledger.append(("admit", self.active_transition))
        return f"request-{self.active_transition}"

    def claim(self, **kwargs: Any) -> str:
        self.ledger.append(("claim", self.active_transition))
        return f"run-{self.active_transition}"

    def start_run(self, **kwargs: Any) -> None:
        self.ledger.append(("start-run", self.active_transition))

    def execute_to_completion(self, run_id: str, *, sync_runtime_networks: bool) -> None:
        self.ledger.append(
            ("execute", (self.active_transition, sync_runtime_networks))
        )
        if self.fail_at == self.active_transition:
            raise self.failure
        self.activity = (
            *self.activity,
            f"{self.active_transition}-effect-attempt-complete",
        )

    def read_current_graph_http(self) -> dict[str, Any]:
        self.ledger.append(("read-http", (self.active_transition, self.current_graph_id)))
        return {"graph_id": self.current_graph_id, "activity": self.activity}

    def read_current_graph_mcp(self) -> dict[str, Any]:
        self.ledger.append(("read-mcp", (self.active_transition, self.current_graph_id)))
        return {"graph_id": self.current_graph_id, "activity": self.activity}

    def advance_current_graph(self, **kwargs: Any) -> str:
        self.current_graph_id = kwargs["desired_graph_id"]
        self.ledger.append(("advance", (self.active_transition, self.current_graph_id)))
        return self.current_graph_id

    def read_activity_http(self) -> dict[str, Any]:
        self.ledger.append(("history-http", self.activity))
        return {"events": self.activity}

    def read_activity_mcp(self) -> dict[str, Any]:
        self.ledger.append(("history-mcp", self.activity))
        return {"events": self.activity}


@dataclass
class RecordingBlueGreenEffects:
    responses: list[bytes] = field(
        default_factory=lambda: [response for _, response in RESPONSES]
    )
    ledger: list[tuple[str, Any]] = field(default_factory=list)
    probe_container_id: str | None = None

    def probe_runtime_node(
        self,
        *,
        node_id: str,
        expected_image_reference: str,
        labelled: bool,
        attach_runtime_network: bool,
    ) -> dict[str, Any]:
        if self.probe_container_id is None:
            self.probe_container_id = "candidate-blue-green-probe"
            self.ledger.append(("probe-created", self.probe_container_id))
        response = self.responses.pop(0)
        self.ledger.append(
            (
                "probe",
                {
                    "node_id": node_id,
                    "expected_image_reference": expected_image_reference,
                    "labelled": labelled,
                    "attach_runtime_network": attach_runtime_network,
                    "response": response,
                },
            )
        )
        return {
            "response": response,
            "container_id": self.probe_container_id,
            "request_origin": "inside-probe",
            "target_image_id": "sha256:" + "7" * 64,
            "target_image_reference": expected_image_reference,
        }

    def remove_probe(self) -> None:
        if self.probe_container_id is not None:
            self.ledger.append(("remove-probe", self.probe_container_id))
            self.probe_container_id = None

    def cleanup(self, *, reason: str) -> dict[str, Any]:
        self.ledger.append(("cleanup", reason))
        return {
            "containers": (),
            "networks": (),
            "volumes": (),
            "images": (),
            "postgres_relations": (),
            "foreign_canary_after": (FOREIGN_RESOURCE_CANARY,),
        }


class CandidateBlueGreenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = importlib.import_module(
            "scripts.cpk_server_candidate_topology"
        )
        self.hello_document = self.candidate._product_document(ROOT, "hello_server")
        self.router_document = self.candidate._product_document(
            ROOT,
            "http_active_router",
        )

    def test_blue_green_assembly_profile_is_closed_and_attests_router(self) -> None:
        profile = deepcopy(
            getattr(self.candidate, "EXPECTED_BLUE_GREEN_ASSEMBLY", {})
        )

        with self.subTest(boundary="scenario-is-blue-green"):
            self.assertEqual(profile.get("scenario"), BLUE_GREEN_SCENARIO)
        with self.subTest(boundary="router-coordinate-is-exact"):
            self.assertEqual(
                profile.get("products", {}).get("http_active_router"),
                {
                    "classification": "published-digest",
                    "reference": ROUTER_IMAGE,
                    "descriptor_sha256": ROUTER_DESCRIPTOR_SHA256,
                },
            )
        with self.subTest(boundary="single-hello-profile-remains-unchanged"):
            self.assertEqual(
                self.candidate.EXPECTED_ASSEMBLY,
                exact_assembly(),
            )
        with self.subTest(boundary="profile-has-no-provider-or-secret-material"):
            rendered = json.dumps(profile, sort_keys=True)
            for protected in (
                "ACTIVE_TARGET_URL",
                "docker.sock",
                "candidate-password",
                "secret://",
            ):
                self.assertNotIn(protected, rendered)

    def test_graph_values_preserve_coexistence_and_change_only_active_connection(
        self,
    ) -> None:
        builder: Callable[..., DeploymentGraph] = getattr(
            self.candidate,
            "_candidate_blue_green_graph",
            lambda **_kwargs: DeploymentGraph("candidate-topology-1714"),
        )
        graphs = {
            "blue": builder(
                hello_document=self.hello_document,
                router_document=self.router_document,
                workspace_id="candidate-topology-1714",
                present_roles=("hello-blue",),
                active_role="hello-blue",
            ),
            "prepared": builder(
                hello_document=self.hello_document,
                router_document=self.router_document,
                workspace_id="candidate-topology-1714",
                present_roles=("hello-blue", "hello-green"),
                active_role="hello-blue",
            ),
            "green": builder(
                hello_document=self.hello_document,
                router_document=self.router_document,
                workspace_id="candidate-topology-1714",
                present_roles=("hello-blue", "hello-green"),
                active_role="hello-green",
            ),
            "retired": builder(
                hello_document=self.hello_document,
                router_document=self.router_document,
                workspace_id="candidate-topology-1714",
                present_roles=("hello-green",),
                active_role="hello-green",
            ),
        }

        expected_nodes = {
            "blue": {"hello-blue", "router"},
            "prepared": {"hello-blue", "hello-green", "router"},
            "green": {"hello-blue", "hello-green", "router"},
            "retired": {"hello-green", "router"},
        }
        for name, expected in expected_nodes.items():
            with self.subTest(boundary=f"{name}-complete-graph"):
                self.assertEqual(set(graphs[name].nodes), expected)
        expected_edges = {
            "blue": (("hello-blue", "internal", "router", "active"),),
            "prepared": (("hello-blue", "internal", "router", "active"),),
            "green": (("hello-green", "internal", "router", "active"),),
            "retired": (("hello-green", "internal", "router", "active"),),
        }
        for name, expected in expected_edges.items():
            with self.subTest(boundary=f"{name}-sole-active-connection"):
                self.assertEqual(_edge_roles(graphs[name]), expected)
        with self.subTest(boundary="cutover-preserves-both-server-values"):
            for role in ("hello-blue", "hello-green"):
                self.assertEqual(
                    graphs["prepared"].nodes.get(role),
                    graphs["green"].nodes.get(role),
                )
        with self.subTest(boundary="router-target-is-derived-only-from-edge"):
            source = Path(self.candidate.__file__).read_text(encoding="utf-8")
            self.assertNotIn("ACTIVE_TARGET_URL", source)

    def test_public_sequence_proves_blue_green_rollback_retirement_and_history(
        self,
    ) -> None:
        ledger: list[tuple[str, Any]] = []
        workflow = RecordingBlueGreenWorkflow(ledger=ledger)
        effects = RecordingBlueGreenEffects(ledger=ledger)
        runner = getattr(
            self.candidate,
            "run_candidate_blue_green",
            lambda *_args, **_kwargs: {},
        )
        report = runner(
            deepcopy(getattr(self.candidate, "EXPECTED_BLUE_GREEN_ASSEMBLY", {})),
            inspection=exact_inspection(),
            workflow=workflow,
            effects=effects,
            hello_document=self.hello_document,
            router_document=self.router_document,
            empty_graph=DeploymentGraph("candidate-topology-1714"),
            current_graph_id="graph-predecessor",
            prepared={
                "build": {"image_id": CANDIDATE_IMAGE_ID},
                "preflight": {
                    "inventory": deepcopy(FOREIGN_INVENTORY),
                    "foreign_canary_before": (FOREIGN_RESOURCE_CANARY,),
                },
                "server": None,
            },
        )

        plans = tuple(value for name, value in workflow.ledger if name == "plan")
        with self.subTest(boundary="exact-public-transition-order"):
            self.assertEqual(plans, TRANSITIONS)
        with self.subTest(boundary="every-execution-disables-network-repair"):
            self.assertEqual(
                tuple(
                    value
                    for name, value in workflow.ledger
                    if name == "execute"
                ),
                tuple((title, False) for title in TRANSITIONS),
            )
        with self.subTest(boundary="exact-desired-version-fencing"):
            self.assertEqual(
                workflow.expected_predecessors,
                {
                    "blue-realization": None,
                    "green-preparation": "graph-blue-realization",
                    "green-cutover": "graph-green-preparation",
                    "rollback-blue": "graph-green-cutover",
                    "final-green": "graph-rollback-blue",
                    "retire-blue": "graph-final-green",
                    "teardown": "graph-retire-blue",
                },
            )
        observed_responses = tuple(
            (entry.get("stage"), entry.get("response"))
            for entry in report.get("blue_green", {}).get("responses", ())
        )
        with self.subTest(boundary="every-user-visible-response-is-exact"):
            self.assertEqual(
                observed_responses,
                tuple((stage, body.decode("ascii")) for stage, body in RESPONSES),
            )
        with self.subTest(boundary="every-live-stage-is-user-visible"):
            self.assertEqual(
                tuple(stage.get("name") for stage in report.get("stages", ())),
                (
                    "admission",
                    "build",
                    "blue-realization",
                    "green-preparation",
                    "green-cutover",
                    "rollback-blue",
                    "final-green",
                    "retire-blue",
                    "teardown",
                    "cleanup",
                ),
            )
        transitions = report.get("workflow", {}).get("transitions", ())
        with self.subTest(boundary="http-mcp-parity-at-every-boundary"):
            self.assertEqual(len(transitions), len(TRANSITIONS))
            for transition in transitions:
                self.assertEqual(
                    transition.get("predecessor_http"),
                    transition.get("predecessor_mcp"),
                )
                self.assertEqual(
                    transition.get("successor_http"),
                    transition.get("successor_mcp"),
                )
        history = report.get("workflow", {})
        with self.subTest(boundary="rollback-preserves-green-cutover-history"):
            self.assertEqual(history.get("history_http"), history.get("history_mcp"))
            self.assertEqual(
                history.get("history_http", {}).get("events"),
                tuple(f"{title}-effect-attempt-complete" for title in TRANSITIONS),
            )
        green_observations = [
            index
            for index, entry in enumerate(ledger)
            if entry[0] == "probe" and entry[1]["response"] == GREEN_RESPONSE
        ]
        retire_plans = [
            index
            for index, entry in enumerate(ledger)
            if entry == ("plan", "retire-blue")
        ]
        with self.subTest(boundary="three-green-observations-are-explicit"):
            self.assertEqual(len(green_observations), 3)
        with self.subTest(boundary="blue-retires-only-after-final-green-observation"):
            self.assertTrue(
                len(green_observations) == 3
                and len(retire_plans) == 1
                and green_observations[1] < retire_plans[0]
            )
        with self.subTest(boundary="probe-sequence-is-total"):
            self.assertEqual(
                [entry[1]["response"] for entry in ledger if entry[0] == "probe"],
                [body for _, body in RESPONSES],
            )
        with self.subTest(boundary="one-probe-is-reused-across-live-stages"):
            self.assertEqual(
                [entry for entry in ledger if entry[0] == "probe-created"],
                [("probe-created", "candidate-blue-green-probe")],
            )
        with self.subTest(boundary="probe-is-removed-once-before-teardown"):
            removals = [
                index
                for index, entry in enumerate(ledger)
                if entry[0] == "remove-probe"
            ]
            teardown_plans = [
                index
                for index, entry in enumerate(ledger)
                if entry == ("plan", "teardown")
            ]
            final_probes = [
                index for index, entry in enumerate(ledger) if entry[0] == "probe"
            ]
            self.assertEqual(len(removals), 1)
            self.assertEqual(len(teardown_plans), 1)
            self.assertEqual(len(final_probes), 6)
            self.assertLess(final_probes[-1], removals[0])
            self.assertLess(removals[0], teardown_plans[0])
        with self.subTest(boundary="terminal-report-is-closed-and-redacted"):
            self.assertEqual(report.get("status"), "passed")
            self.assertEqual(report.get("first_failed_stage"), None)
            self.assertEqual(
                report.get("report_sha256"),
                self.candidate._report_sha256(report),
            )
            rendered = json.dumps(report, sort_keys=True)
            for protected in (
                "ACTIVE_TARGET_URL",
                "candidate-password",
                "docker.sock",
                "protected-",
            ):
                self.assertNotIn(protected, rendered)

    def test_failed_green_preparation_leaves_blue_active_without_cutover(self) -> None:
        failure = RuntimeError("protected-green-preparation-failure")
        ledger: list[tuple[str, Any]] = []
        workflow = RecordingBlueGreenWorkflow(
            ledger=ledger,
            fail_at="green-preparation",
            failure=failure,
        )
        effects = RecordingBlueGreenEffects(ledger=ledger)
        runner = getattr(
            self.candidate,
            "run_candidate_blue_green",
            lambda *_args, **_kwargs: None,
        )
        escaped: BaseException | None = None
        try:
            runner(
                deepcopy(getattr(self.candidate, "EXPECTED_BLUE_GREEN_ASSEMBLY", {})),
                inspection=exact_inspection(),
                workflow=workflow,
                effects=effects,
                hello_document=self.hello_document,
                router_document=self.router_document,
                empty_graph=DeploymentGraph("candidate-topology-1714"),
                current_graph_id="graph-predecessor",
                prepared={
                    "build": {"image_id": CANDIDATE_IMAGE_ID},
                    "preflight": {
                        "inventory": deepcopy(FOREIGN_INVENTORY),
                        "foreign_canary_before": (FOREIGN_RESOURCE_CANARY,),
                    },
                    "server": None,
                },
            )
        except BaseException as error:
            escaped = error

        with self.subTest(boundary="original-green-preparation-error-surfaces"):
            self.assertIs(escaped, failure)
        with self.subTest(boundary="blue-remains-current"):
            self.assertEqual(workflow.current_graph_id, "graph-blue-realization")
        with self.subTest(boundary="cutover-never-planned"):
            self.assertNotIn(("plan", "green-cutover"), workflow.ledger)
        with self.subTest(boundary="failure-cannot-claim-green-observation"):
            report = getattr(escaped, "candidate_terminal_report", {})
            rendered = json.dumps(report, sort_keys=True)
            self.assertEqual(report.get("status"), "failed")
            self.assertEqual(report.get("first_failed_stage"), "green-preparation")
            self.assertNotIn("Hello from green", rendered)
            self.assertNotIn("protected-green-preparation-failure", rendered)
        with self.subTest(boundary="failure-uses-exact-owned-cleanup"):
            self.assertEqual(ledger[-1:], [("cleanup", "error")])

    def test_existing_candidate_main_and_smoke_select_blue_green_without_new_harness(
        self,
    ) -> None:
        candidate_source = Path(self.candidate.__file__).read_text(encoding="utf-8")
        smoke_source = (
            ROOT / "scripts" / "cpk_server_candidate_topology_smoke.sh"
        ).read_text(encoding="utf-8")

        with self.subTest(boundary="main-admits-closed-scenario-selector"):
            self.assertIn(
                'choices=("single-hello", "blue-green")',
                candidate_source,
            )
        with self.subTest(boundary="main-dispatches-existing-blue-green-runner"):
            self.assertIn("run_candidate_blue_green(", candidate_source)
        with self.subTest(boundary="smoke-forwards-explicit-scenario"):
            self.assertIn('CPK_CANDIDATE_SCENARIO', smoke_source)
            self.assertIn('--scenario "$CPK_CANDIDATE_SCENARIO"', smoke_source)
        with self.subTest(boundary="smoke-retains-one-authoritative-runner"):
            self.assertEqual(
                smoke_source.count(
                    "python -m scripts.cpk_server_candidate_topology"
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
