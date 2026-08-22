from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from control_plane_kit_core.topology import DeploymentGraph

from candidate_topology_fixture import (
    CANDIDATE_COMMIT,
    CANDIDATE_IMAGE_ID,
    CANDIDATE_LABELS,
    CANDIDATE_SERVER_ENVIRONMENT,
    CANDIDATE_TREE,
    CPK_SERVER_BASE_IMAGE,
    CORE_WHEEL_SHA256,
    CURL_IMAGE,
    DOCKER_SOCKET_GID,
    FOREIGN_INVENTORY,
    FOREIGN_RESOURCE_CANARY,
    HELLO_DESCRIPTOR_SHA256,
    HELLO_IMAGE,
    HELLO_LOCAL_IMAGE_ID,
    HELLO_RESPONSE,
    HELLO_RESPONSE_SHA256,
    INSTALLED_MODULE_PATHS,
    INSTALLED_RECORD_PATHS,
    INTERPRETERS_COMMIT,
    INTERPRETERS_TREE,
    OPERATIONS_WHEEL_SHA256,
    OPERATOR_SCOPES,
    POSTGRES_BOOTSTRAP_ENVIRONMENT,
    POSTGRES_DB,
    POSTGRES_DSN_ENVIRONMENT,
    POSTGRES_IMAGE,
    POSTGRES_PASSWORD,
    POSTGRES_READY_ATTEMPTS,
    POSTGRES_READY_RETRY_SECONDS,
    POSTGRES_USER,
    PRODUCTION_DOCKERFILE_SHA256,
    RecordingCandidateEffects,
    RecordingCandidateEffectsFactory,
    RecordingDockerClient,
    RecordingDockerContainer,
    RecordingDockerImage,
    RecordingDockerNetwork,
    RecordingHostedWorkflow,
    RecordingHostedWorkflowFactory,
    RUNNER_COMMIT,
    RUNNER_TREE,
    SECRETS_COMMIT,
    SECRETS_TREE,
    SERVER_BASELINE_COMMIT,
    SERVER_BASELINE_TREE,
    SNAPSHOT_MANIFEST_SHA256,
    WORKSPACE_ID,
    WORKER_SCOPES,
    canonical_sha256,
    canonical_report_sha256,
    changed,
    exact_assembly,
    exact_inspection,
)


ROOT = Path(__file__).resolve().parents[1]
ASSEMBLY_ERROR = "candidate assembly is invalid"
WORKFLOW_ERROR = "candidate topology workflow failed"
HELLO_PUBLIC_SEQUENCE = (
    ("plan", "hello"),
    ("desired", "hello"),
    ("plan", "hello"),
    ("request-approval", "hello"),
    ("approval-visible", "hello"),
    ("approve", "hello"),
    ("admit", "hello"),
    ("claim", "hello"),
    ("start", "hello"),
    ("execute", ("hello", False)),
)
EMPTY_PUBLIC_SEQUENCE = (
    ("plan", "empty"),
    ("desired", "empty"),
    ("plan", "empty"),
    ("request-approval", "empty"),
    ("approval-visible", "empty"),
    ("approve", "empty"),
    ("admit", "empty"),
    ("claim", "empty"),
    ("start", "empty"),
    ("execute", ("empty", False)),
)
EXPECTED_EVIDENCE_CLASSIFICATIONS = {
    "candidate-server-attestation": "candidate-direct",
    "public-workflow": "candidate-direct",
    "predecessor-readback": "candidate-direct",
    "hello-response": "candidate-direct",
    "empty-successor": "candidate-direct",
    "residue": "candidate-direct",
    "external-package-coordinate": "supporting",
    "hello-image": "published-digest",
    "postgres-image": "published-digest",
}


class CandidateTopologyAcceptanceTests(unittest.TestCase):
    def test_control_external_coordinates_are_exact_and_immutable(self) -> None:
        self.assertEqual(
            (
                SERVER_BASELINE_COMMIT,
                SERVER_BASELINE_TREE,
                CANDIDATE_COMMIT,
                CANDIDATE_TREE,
                SNAPSHOT_MANIFEST_SHA256,
                INTERPRETERS_COMMIT,
                INTERPRETERS_TREE,
                SECRETS_COMMIT,
                SECRETS_TREE,
                PRODUCTION_DOCKERFILE_SHA256,
                CPK_SERVER_BASE_IMAGE,
                CANDIDATE_IMAGE_ID,
                POSTGRES_IMAGE,
                HELLO_IMAGE,
                HELLO_DESCRIPTOR_SHA256,
            ),
            (
                "43e9f359ca828c83fe4994ed1b62e1be54277ddd",
                "ec259176eba3ce2f777d38c68fcc14e0a0e80cd3",
                "4fb75b7b6c1a16ec3b8c1d78dec6ad1a4ad1b40a",
                "6a405e4ab7e707ff7374205ca2ef4726d6225b86",
                "9e9492ed1afe80fc77e12b6c7ba8a5a740a7548a0ccce0056c48038a18d6d403",
                "2335a21adc5c0b0ae2f592bd15757c6ca1a55e4b",
                "343911ecc968d0ea6c3b1c128a3aad4a28471cfe",
                "96e86dc3248d578780d64d5d7fc5d6359631d1d6",
                "b1740225a93410349a9e9199c539e330b408abae",
                "aa0f6971fac329ab191f5d1b7aa21617ca2ea1fc69ef4abad748ec217a6239b6",
                "sha256:" + "9" * 64,
                "sha256:" + "f" * 64,
                "docker.io/library/postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777",
                "ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:e2288b23844b1f0b7526d2798cbc1eaf6e9f536399173a043e7957f0e7730cbf",
                "57ac661ca3f73ad4fa488df34390240e95da58e302bffb17c2197eeac29c2a24",
            ),
        )
        self.assertNotEqual(CPK_SERVER_BASE_IMAGE, CANDIDATE_IMAGE_ID)

    def test_control_fixture_assembly_is_closed_joined_and_secret_free(self) -> None:
        assembly = exact_assembly()

        self.assertEqual(assembly["server_source"], assembly["runner"])
        self.assertEqual(
            assembly["server_source"],
            {
                "repository": "OpenJ92/control-plane-kit-servers",
                "commit": RUNNER_COMMIT,
                "tree": RUNNER_TREE,
            },
        )
        self.assertEqual(
            {
                "commit": assembly["server_source"]["commit"],
                "tree": assembly["server_source"]["tree"],
            },
            {
                "commit": exact_inspection()["server_source"]["commit"],
                "tree": exact_inspection()["server_source"]["tree"],
            },
        )
        self.assertGreater(len(set(RUNNER_COMMIT)), 8)
        self.assertGreater(len(set(RUNNER_TREE)), 8)
        self.assertEqual(
            assembly["products"]["cpk_server"]["source_commit"],
            assembly["candidate"]["commit"],
        )
        self.assertEqual(
            assembly["products"]["cpk_server"]["source_tree"],
            assembly["candidate"]["tree"],
        )
        self.assertEqual(
            set(assembly),
            {
                "schema",
                "scenario",
                "acceptance_level",
                "candidate",
                "server_source",
                "runner",
                "dependencies",
                "products",
                "inputs",
            },
        )
        self.assertNotIn("image_id", assembly["products"]["cpk_server"])
        rendered = json.dumps(assembly, sort_keys=True).lower()
        for forbidden in ("password", "credential", "plaintext", "ciphertext", "token"):
            self.assertNotIn(forbidden, rendered)

    def test_control_recorders_expose_public_phases_without_runtime_repair(self) -> None:
        ledger = []
        workflow = RecordingHostedWorkflow(ledger=ledger)
        effects = RecordingCandidateEffects(ledger=ledger)

        session_id = workflow.start_session("hello")
        desired_graph_id = workflow.set_desired_graph(
            session_id=session_id,
            graph=DeploymentGraph(WORKSPACE_ID),
            title="hello",
            expected_desired_graph_id=None,
        )
        plan_id = workflow.plan_transition(
            session_id=session_id,
            desired_graph_id=desired_graph_id,
        )
        approval = workflow.request_approval(
            session_id=session_id,
            plan_id=plan_id,
        )
        workflow.assert_approval_visible(approval["request_id"], plan_id)
        workflow.approve(session_id=session_id, approval=approval)
        request_id = workflow.admit(session_id=session_id, plan_id=plan_id)
        run_id = workflow.claim(request_id=request_id)
        workflow.start_run(run_id=run_id)
        workflow.execute_to_completion(run_id, sync_runtime_networks=False)
        predecessor_http = workflow.read_current_graph_http()
        predecessor_mcp = workflow.read_current_graph_mcp()
        body = effects.probe_hello(labelled=True, attach_runtime_network=True)
        effects.remove_probe()

        self.assertEqual(predecessor_http, predecessor_mcp)
        self.assertEqual(body, HELLO_RESPONSE)
        self.assertIs(workflow.ledger, ledger)
        self.assertIs(effects.ledger, ledger)
        self.assertEqual(
            ledger,
            [
                *HELLO_PUBLIC_SEQUENCE,
                ("hello-predecessor-http", "graph-predecessor"),
                ("hello-predecessor-mcp", "graph-predecessor"),
                ("probe", (True, True)),
                ("remove-probe", None),
            ],
        )

    def test_exact_assembly_and_server_source_are_admitted_without_reconstruction(self) -> None:
        candidate = self._candidate_module()
        assembly = exact_assembly()
        admission_error = None
        admitted = None
        try:
            admitted = candidate.admit_candidate_assembly(
                assembly,
                exact_inspection(),
            )
        except candidate.CandidateAssemblyError as error:
            admission_error = error

        self.assertIsNone(
            admission_error,
            "relational server source admission is not published",
        )
        if admission_error is None:
            self.assertIs(admitted, assembly)
            self.assertEqual(admitted["server_source"], admitted["runner"])
            self.assertEqual(canonical_sha256(admitted), canonical_sha256(assembly))

    def test_missing_extra_wrong_and_malformed_assembly_values_fail_closed(self) -> None:
        candidate = self._candidate_module()
        exact = exact_assembly()
        rows = []
        missing = deepcopy(exact)
        del missing["server_source"]
        rows.append(("missing", missing))
        rows.append(("extra", {**exact, "branch": "develop"}))
        rows.extend(
            (
                name,
                changed(exact, path, value),
            )
            for name, path, value in (
                ("wrong-candidate", ("candidate", "commit"), "0" * 40),
                ("wrong-server-tree", ("server_source", "tree"), "1" * 40),
                ("runner-drift", ("runner", "commit"), "2" * 40),
                ("mutable-reference", ("products", "hello", "reference"), "hello:latest"),
                ("malformed-hash", ("products", "cpk_server", "dockerfile_sha256"), "ABC"),
                ("wrong-classification", ("products", "cpk_server", "classification"), "published-digest"),
            )
        )

        for name, document in rows:
            with self.subTest(name=name):
                with self.assertRaisesRegex(candidate.CandidateAssemblyError, ASSEMBLY_ERROR) as caught:
                    candidate.admit_candidate_assembly(document, exact_inspection())
                self.assertIsNone(caught.exception.__cause__)
                self.assertIsNone(caught.exception.__context__)

    def test_dirty_mutated_or_incomplete_inputs_abort_before_docker(self) -> None:
        candidate = self._candidate_module()
        assembly = exact_assembly()
        rows = []
        dirty = exact_inspection()
        dirty["candidate"]["clean"] = False
        rows.append(("dirty-candidate", assembly, dirty))
        dirty_server = exact_inspection()
        dirty_server["server_source"]["clean"] = False
        rows.append(("dirty-server", assembly, dirty_server))
        mutated = exact_inspection()
        mutated["files"]["products/cpk_server/Dockerfile"] = "0" * 64
        rows.append(("production-dockerfile", assembly, mutated))
        incomplete = exact_inspection()
        del incomplete["files"]["dist/control_plane_kit_operations.whl"]
        rows.append(("missing-wheel", assembly, incomplete))
        extra = exact_inspection()
        extra["files"]["dist/foreign.whl"] = "1" * 64
        rows.append(("extra-build-input", assembly, extra))
        rows.extend(
            (
                name,
                (
                    changed(assembly, assembly_path, value)
                    if assembly_path is not None
                    else assembly
                ),
                (
                    changed(exact_inspection(), inspection_path, value)
                    if inspection_path is not None
                    else exact_inspection()
                ),
            )
            for name, assembly_path, inspection_path, value in (
                (
                    "cpk-server-base-image-drift",
                    None,
                    ("images", "cpk_server_base"),
                    "sha256:" + "3" * 64,
                ),
                (
                    "candidate-result-image-drift",
                    ("products", "cpk_server", "image_id"),
                    None,
                    "sha256:" + "4" * 64,
                ),
                (
                    "acceptance-overlay-drift",
                    None,
                    ("files", "acceptance/candidate_topology/Dockerfile"),
                    "5" * 64,
                ),
                (
                    "core-wheel-drift",
                    None,
                    ("files", "dist/control_plane_kit_core.whl"),
                    "6" * 64,
                ),
                (
                    "operations-wheel-drift",
                    None,
                    ("files", "dist/control_plane_kit_operations.whl"),
                    "7" * 64,
                ),
            )
        )

        for name, candidate_assembly, inspection in rows:
            with self.subTest(name=name):
                ledger = []
                effects = RecordingCandidateEffects(ledger=ledger)
                with self.assertRaisesRegex(candidate.CandidateAssemblyError, ASSEMBLY_ERROR):
                    candidate.run_candidate_topology(
                        candidate_assembly,
                        inspection=inspection,
                        workflow=RecordingHostedWorkflow(ledger=ledger),
                        effects=effects,
                    )
                self.assertEqual(ledger, [])

    def test_report_attests_overlay_wheels_records_modules_and_live_image(self) -> None:
        candidate = self._candidate_module()
        ledger = []
        with self._admission_bridge(candidate):
            report = candidate.run_candidate_topology(
                exact_assembly(),
                inspection=exact_inspection(),
                workflow=RecordingHostedWorkflow(ledger=ledger),
                effects=RecordingCandidateEffects(ledger=ledger),
            )

        self.assertEqual(report["schema"], "cpk.candidate-topology-report.v1")
        self.assertEqual(report["assembly"], exact_assembly())
        self.assertEqual(
            report["external_coordinates"],
            {
                "server_baseline_commit": SERVER_BASELINE_COMMIT,
                "server_baseline_tree": SERVER_BASELINE_TREE,
                "snapshot_manifest_sha256": SNAPSHOT_MANIFEST_SHA256,
                "postgres_image": POSTGRES_IMAGE,
            },
        )
        attestation = report["attestation"]
        self.assertEqual(attestation["production_dockerfile_sha256"], PRODUCTION_DOCKERFILE_SHA256)
        self.assertNotEqual(
            attestation["production_dockerfile_sha256"],
            attestation["acceptance_overlay_sha256"],
        )
        self.assertEqual(
            attestation["wheel_sha256"],
            {
                "control-plane-kit-core": CORE_WHEEL_SHA256,
                "control-plane-kit-operations": OPERATIONS_WHEEL_SHA256,
            },
        )
        self.assertEqual(attestation["base_image"], CPK_SERVER_BASE_IMAGE)
        self.assertEqual(attestation["image_id"], CANDIDATE_IMAGE_ID)
        self.assertNotIn("image_id", exact_assembly()["products"]["cpk_server"])
        self.assertNotEqual(attestation["base_image"], attestation["image_id"])
        self.assertEqual(
            ledger[0],
            (
                "build",
                (canonical_sha256(exact_assembly()), CPK_SERVER_BASE_IMAGE),
            ),
        )
        self.assertEqual(attestation["record_paths"], INSTALLED_RECORD_PATHS)
        self.assertEqual(attestation["module_paths"], INSTALLED_MODULE_PATHS)

    def test_main_publishes_exact_injectable_composition_seam(self) -> None:
        candidate = self._candidate_module()
        parameters = inspect.signature(candidate.main).parameters

        with self.subTest(publication="workflow-and-effects-factories"):
            self.assertEqual(
                tuple(
                    name
                    for name in parameters
                    if name in {"workflow_factory", "effects_factory"}
                ),
                ("workflow_factory", "effects_factory"),
            )

    def test_main_report_is_derived_from_explicit_build_inspection_and_probe_data(self) -> None:
        result = self._invoke_main(use_predecessor_bridge=True)
        report = result["report"] or {}
        attestation = report.get("attestation", {})
        ledger = result["ledger"]
        names = tuple(name for name, _ in ledger)
        workflow = (
            result["workflow_factory"].instances[0]
            if result["workflow_factory"].instances
            else None
        )
        graphs = workflow.graphs if workflow is not None else {}
        hello_graph = graphs.get("hello")
        empty_graph = graphs.get("empty")
        hello_node = (
            next(iter(hello_graph.nodes.values()), None)
            if type(hello_graph) is DeploymentGraph
            else None
        )
        metadata = getattr(hello_node, "metadata", {})
        imports = tuple(value for name, value in ledger if name == "import-product")

        with self.subTest(boundary="legacy-bridge-is-bounded-and-recorded"):
            self.assertEqual(
                bool(result["bridge"]),
                not result["injectable_main"],
            )
        with self.subTest(boundary="real-main-completes"):
            self.assertIsNone(result["escaped"])
        with self.subTest(boundary="observed-bootstrap-order"):
            self.assertEqual(
                tuple(
                    name
                    for name in names
                    if name
                    in {
                        "preflight-inventory",
                        "build",
                        "start-candidate-server",
                        "inspect-candidate-server",
                        "workflow-target",
                        "create-workspace",
                        "import-product",
                        "register-runtime-authority",
                        "register-runtime-delivery",
                    }
                ),
                (
                    "preflight-inventory",
                    "build",
                    "start-candidate-server",
                    "inspect-candidate-server",
                    "workflow-target",
                    "create-workspace",
                    "register-runtime-authority",
                    "register-runtime-delivery",
                    "import-product",
                ),
            )
        with self.subTest(boundary="hello-descriptor"):
            self.assertEqual(
                imports,
                (
                    {
                        "label": "hello",
                        "content_digest": HELLO_DESCRIPTOR_SHA256,
                        "document_sha256": HELLO_DESCRIPTOR_SHA256,
                    },
                ),
            )
        with self.subTest(boundary="hello-graph"):
            self.assertIs(type(hello_graph), DeploymentGraph)
        with self.subTest(boundary="hello-product-identity"):
            self.assertEqual(
                metadata.get("product_identity"),
                "control-plane-kit/hello-server/1",
            )
        with self.subTest(boundary="hello-product-digest"):
            self.assertEqual(
                metadata.get("product_descriptor_digest"),
                HELLO_DESCRIPTOR_SHA256,
            )
        with self.subTest(boundary="empty-graph"):
            self.assertEqual(empty_graph, DeploymentGraph(WORKSPACE_ID))
        with self.subTest(boundary="built-server-dataflow"):
            self.assertEqual(
                tuple(
                    item
                    for item in ledger
                    if item[0]
                    in {
                        "start-candidate-server",
                        "inspect-candidate-server",
                        "workflow-target",
                    }
                ),
                (
                    ("start-candidate-server", CANDIDATE_IMAGE_ID),
                    ("inspect-candidate-server", "candidate-server-container"),
                    (
                        "workflow-target",
                        {
                            "base_url": "http://candidate-server-container:8080",
                            "workspace_id": WORKSPACE_ID,
                            "server_container": "candidate-server-container",
                        },
                    ),
                ),
            )
        with self.subTest(boundary="terminal-report"):
            self.assertTrue(report)
        with self.subTest(boundary="attestation-dataflow"):
            self.assertEqual(
                attestation,
                {
                    **attestation,
                    "base_image": CPK_SERVER_BASE_IMAGE,
                    "image_id": CANDIDATE_IMAGE_ID,
                    "server_container_id": "candidate-server-container",
                    "server_container_image_id": CANDIDATE_IMAGE_ID,
                    "record_paths": list(INSTALLED_RECORD_PATHS),
                    "module_paths": list(INSTALLED_MODULE_PATHS),
                    "record_origins": {
                        path: CANDIDATE_IMAGE_ID for path in INSTALLED_RECORD_PATHS
                    },
                    "module_origins": {
                        path: CANDIDATE_IMAGE_ID for path in INSTALLED_MODULE_PATHS
                    },
                },
            )
        with self.subTest(boundary="probe-dataflow"):
            self.assertEqual(
                report.get("hello"),
                {
                    "response": HELLO_RESPONSE.decode("ascii"),
                    "response_sha256": HELLO_RESPONSE_SHA256,
                    "container_id": "candidate-consumer-probe",
                    "request_origin": "inside-probe",
                    "target_image_id": HELLO_LOCAL_IMAGE_ID,
                    "target_image_reference": HELLO_IMAGE,
                    "controller_network_repair": False,
                    "server_network_repair": False,
                },
            )
        observations = report.get("observations", {})
        cleanup = report.get("cleanup", {})
        with self.subTest(boundary="foreign-residue-preserved"):
            self.assertEqual(
                observations.get("pre_inventory"),
                json.loads(json.dumps(FOREIGN_INVENTORY)),
            )
            self.assertEqual(
                observations.get("post_inventory"),
                observations.get("pre_inventory"),
            )
            self.assertEqual(
                cleanup.get("foreign_canary_after"),
                [FOREIGN_RESOURCE_CANARY],
            )
        with self.subTest(boundary="owned-residue-absent"):
            self.assertTrue(cleanup)
            rendered_cleanup = json.dumps(cleanup, sort_keys=True)
            for owned in (
                "candidate-server-container",
                "candidate-consumer-probe",
                CANDIDATE_IMAGE_ID,
                "candidate-build-1714",
            ):
                self.assertNotIn(owned, rendered_cleanup)
        with self.subTest(boundary="postgres-is-observed-ephemeral"):
            self.assertEqual(observations.get("postgres_relations"), [])
            self.assertFalse(
                any("sql" in name.lower() for name, _ in ledger),
            )

    def test_wrong_hello_bytes_fail_redacted_and_publish_terminal_report(self) -> None:
        candidate = self._candidate_module()
        result = self._invoke_main(
            wrong_hello=True,
            use_predecessor_bridge=True,
        )
        error = result["escaped"]
        report = result["report"] or {}

        with self.subTest(boundary="fixed-error"):
            self.assertIs(type(error), candidate.CandidateTopologyError)
            if type(error) is candidate.CandidateTopologyError:
                self.assertEqual(str(error), WORKFLOW_ERROR)
                self.assertIsNone(error.__cause__)
                self.assertIsNone(error.__context__)
        with self.subTest(boundary="redaction"):
            self.assertNotIn("Wrong response", str(error))
            self.assertNotIn("Wrong response", json.dumps(report, sort_keys=True))
        with self.subTest(boundary="cleanup"):
            self.assertEqual(
                result["ledger"][-1] if result["ledger"] else None,
                ("cleanup", "error"),
            )
        with self.subTest(boundary="terminal-report"):
            self.assertEqual(report.get("status"), "failed")
            self.assertEqual(report.get("first_failed_stage"), "probe")
            self.assertEqual(
                report.get("report_sha256"),
                canonical_report_sha256(report),
            )

    def test_observed_collision_rejects_before_build_or_server_start(self) -> None:
        candidate = self._candidate_module()
        result = self._invoke_main(
            collision=True,
            use_predecessor_bridge=True,
        )
        error = result["escaped"]
        names = tuple(name for name, _ in result["ledger"])
        report = result["report"] or {}

        with self.subTest(boundary="fixed-error"):
            self.assertIs(type(error), candidate.CandidateAssemblyError)
            if type(error) is candidate.CandidateAssemblyError:
                self.assertEqual(str(error), ASSEMBLY_ERROR)
                self.assertIsNone(error.__cause__)
                self.assertIsNone(error.__context__)
        with self.subTest(boundary="observed-collision"):
            observations = tuple(
                value for name, value in result["ledger"]
                if name == "preflight-inventory"
            )
            self.assertEqual(len(observations), 1)
            if observations:
                self.assertEqual(
                    observations[0].get("collisions"),
                    (("container", "candidate-owned-name"),),
                )
        with self.subTest(boundary="zero-mutation"):
            self.assertNotIn("build", names)
            self.assertNotIn("start-candidate-server", names)
        with self.subTest(boundary="terminal-report"):
            self.assertEqual(report.get("status"), "failed")
            self.assertEqual(report.get("first_failed_stage"), "admission")
            self.assertEqual(
                report.get("report_sha256"),
                canonical_report_sha256(report),
            )

    def test_main_persists_one_terminal_report_for_success_and_each_failure(self) -> None:
        rows = (
            ("success", None, None),
            ("build", "build", "build"),
            ("workflow", "workflow", "workflow"),
            ("probe", "probe", "probe"),
        )
        for name, fail_at, expected_stage in rows:
            with self.subTest(name=name):
                result = self._invoke_main(
                    fail_at=fail_at,
                    use_predecessor_bridge=True,
                )
                report = result["report"] or {}
                self.assertEqual(report.get("first_failed_stage"), expected_stage)
                self.assertEqual(
                    report.get("report_sha256"),
                    canonical_report_sha256(report),
                )
                self.assertEqual(
                    report.get("status"),
                    "passed" if expected_stage is None else "failed",
                )
                cleanup = report.get("cleanup", {})
                self.assertEqual(
                    cleanup.get("foreign_canary_after"),
                    [FOREIGN_RESOURCE_CANARY],
                )

    def test_each_evidence_row_has_one_exact_non_promoting_classification(self) -> None:
        candidate = self._candidate_module()
        ledger = []
        with self._admission_bridge(candidate):
            report = candidate.run_candidate_topology(
                exact_assembly(),
                inspection=exact_inspection(),
                workflow=RecordingHostedWorkflow(ledger=ledger),
                effects=RecordingCandidateEffects(ledger=ledger),
            )

        rows = report["evidence"]
        self.assertTrue(
            all(set(row) == {"claim", "classification", "coordinate"} for row in rows)
        )
        observed = {row["claim"]: row["classification"] for row in rows}
        self.assertEqual(len(observed), len(rows))
        self.assertEqual(observed, EXPECTED_EVIDENCE_CLASSIFICATIONS)
        self.assertTrue(all(type(value) is str for value in observed.values()))

    def test_public_workflow_reads_predecessor_over_http_and_mcp_before_advance(self) -> None:
        report, _, _, ledger = self._run_candidate()

        hello_start = ledger.index(("plan", "hello"))
        hello_execute = ledger.index(("execute", ("hello", False)))
        self.assertEqual(
            tuple(ledger[hello_start : hello_execute + 1]),
            HELLO_PUBLIC_SEQUENCE,
        )
        predecessor_http = ledger.index(
            ("hello-predecessor-http", "graph-predecessor")
        )
        predecessor_mcp = ledger.index(
            ("hello-predecessor-mcp", "graph-predecessor")
        )
        advance = ledger.index(("advance-hello", "graph-hello"))
        probe = ledger.index(("probe", (True, True)))
        self.assertLess(hello_execute, predecessor_http)
        self.assertLess(predecessor_http, predecessor_mcp)
        self.assertLess(predecessor_mcp, advance)
        self.assertLess(hello_execute, probe)
        self.assertEqual(report["workflow"]["predecessor_http"], report["workflow"]["predecessor_mcp"])
        self.assertEqual(report["workflow"]["predecessor_http"]["graph_id"], "graph-predecessor")
        self.assertEqual(
            report["workflow"]["predecessor_http"]["activity"],
            ("hello-effect-attempt-complete",),
        )

    def test_explicit_advance_precedes_successor_http_and_mcp_readback(self) -> None:
        report, _, _, ledger = self._run_candidate()

        advance = ledger.index(("advance-hello", "graph-hello"))
        successor_http = ledger.index(("hello-successor-http", "graph-hello"))
        successor_mcp = ledger.index(("hello-successor-mcp", "graph-hello"))
        probe = ledger.index(("probe", (True, True)))
        self.assertLess(advance, successor_http)
        self.assertLess(successor_http, successor_mcp)
        self.assertLess(successor_mcp, probe)
        empty_start = ledger.index(("plan", "empty"))
        empty_execute = ledger.index(("execute", ("empty", False)))
        self.assertEqual(
            tuple(ledger[empty_start : empty_execute + 1]),
            EMPTY_PUBLIC_SEQUENCE,
        )
        self.assertEqual(report["workflow"]["successor_http"], report["workflow"]["successor_mcp"])
        self.assertEqual(report["workflow"]["successor_http"]["graph_id"], "graph-hello")

    def test_hello_probe_is_labelled_independent_and_never_repairs_networks(self) -> None:
        report, _, _, ledger = self._run_candidate()

        self.assertTrue(
            all(args[1] is False for name, args in ledger if name == "execute")
        )
        self.assertEqual(
            [item for item in ledger if item[0] in {"probe", "remove-probe"}],
            [("probe", (True, True)), ("remove-probe", None)],
        )
        self.assertEqual(report["hello"]["response"], HELLO_RESPONSE.decode("ascii"))
        self.assertEqual(report["hello"]["response_sha256"], HELLO_RESPONSE_SHA256)
        self.assertFalse(report["hello"]["controller_network_repair"])
        self.assertFalse(report["hello"]["server_network_repair"])

    def test_second_public_transition_reaches_empty_and_preserves_history(self) -> None:
        report, workflow, _, ledger = self._run_candidate()

        self.assertEqual(report["workflow"]["empty_http"], report["workflow"]["empty_mcp"])
        self.assertEqual(report["workflow"]["empty_http"]["graph_id"], "graph-empty")
        self.assertEqual(
            report["workflow"]["empty_predecessor_http"],
            report["workflow"]["empty_predecessor_mcp"],
        )
        self.assertEqual(
            report["workflow"]["empty_predecessor_http"]["graph_id"],
            "graph-hello",
        )
        self.assertEqual(
            report["workflow"]["history_http"],
            report["workflow"]["history_mcp"],
        )
        self.assertEqual(
            report["workflow"]["history_http"]["events"],
            (
                "hello-effect-attempt-complete",
                "empty-effect-attempt-complete",
            ),
        )
        self.assertEqual(workflow.current_graph_id, "graph-empty")
        empty_execute = ledger.index(("execute", ("empty", False)))
        predecessor_http = ledger.index(("empty-predecessor-http", "graph-hello"))
        predecessor_mcp = ledger.index(("empty-predecessor-mcp", "graph-hello"))
        advance = ledger.index(("advance-empty", "graph-empty"))
        empty_http = ledger.index(("empty-successor-http", "graph-empty"))
        empty_mcp = ledger.index(("empty-successor-mcp", "graph-empty"))
        history_http = ledger.index(
            (
                "history-http",
                (
                    "hello-effect-attempt-complete",
                    "empty-effect-attempt-complete",
                ),
            )
        )
        history_mcp = ledger.index(
            (
                "history-mcp",
                (
                    "hello-effect-attempt-complete",
                    "empty-effect-attempt-complete",
                ),
            )
        )
        cleanup = ledger.index(("cleanup", "success"))
        complete = (
            *HELLO_PUBLIC_SEQUENCE,
            ("hello-predecessor-http", "graph-predecessor"),
            ("hello-predecessor-mcp", "graph-predecessor"),
            ("advance-hello", "graph-hello"),
            ("hello-successor-http", "graph-hello"),
            ("hello-successor-mcp", "graph-hello"),
            ("probe", (True, True)),
            ("remove-probe", None),
            *EMPTY_PUBLIC_SEQUENCE,
            ("empty-predecessor-http", "graph-hello"),
            ("empty-predecessor-mcp", "graph-hello"),
            ("advance-empty", "graph-empty"),
            ("empty-successor-http", "graph-empty"),
            ("empty-successor-mcp", "graph-empty"),
            (
                "history-http",
                (
                    "hello-effect-attempt-complete",
                    "empty-effect-attempt-complete",
                ),
            ),
            (
                "history-mcp",
                (
                    "hello-effect-attempt-complete",
                    "empty-effect-attempt-complete",
                ),
            ),
            ("cleanup", "success"),
        )
        self.assertEqual(tuple(ledger[ledger.index(("plan", "hello")) :]), complete)
        probe = ledger.index(("probe", (True, True)))
        remove_probe = ledger.index(("remove-probe", None))
        empty_start = ledger.index(("plan", "empty"))
        self.assertLess(probe, remove_probe)
        self.assertLess(remove_probe, empty_start)
        self.assertEqual(
            sorted(
                (
                    empty_execute,
                    predecessor_http,
                    predecessor_mcp,
                    advance,
                    empty_http,
                    empty_mcp,
                    history_http,
                    history_mcp,
                    cleanup,
                )
            ),
            [
                empty_execute,
                predecessor_http,
                predecessor_mcp,
                advance,
                empty_http,
                empty_mcp,
                history_http,
                history_mcp,
                cleanup,
            ],
        )

    def test_success_cleanup_is_terminal_exact_and_foreign_preserving(self) -> None:
        report, _, _, ledger = self._run_candidate()

        self.assertEqual(ledger[-1], ("cleanup", "success"))
        self.assertEqual(
            report["cleanup"],
            {
                "containers": (),
                "networks": (),
                "volumes": (),
                "images": (),
                "build_residue": (),
                "postgres_relations": (),
                "foreign_canary_after": (FOREIGN_RESOURCE_CANARY,),
            },
        )
        self.assertFalse(report["cleanup"]["volumes"])
        self.assertTrue(report["cleanup_terminal"])

    def test_abort_cleanup_is_bounded_terminal_and_classified(self) -> None:
        candidate = self._candidate_module()
        ledger = []
        effects = RecordingCandidateEffects(ledger=ledger)
        workflow = RecordingHostedWorkflow(ledger=ledger)

        def abort(*args, **kwargs):
            raise KeyboardInterrupt("runner interrupted")

        workflow.execute_to_completion = abort
        with self._admission_bridge(candidate):
            with self.assertRaises(KeyboardInterrupt):
                candidate.run_candidate_topology(
                    exact_assembly(),
                    inspection=exact_inspection(),
                    workflow=workflow,
                    effects=effects,
                )

        self.assertEqual(ledger[-1], ("cleanup", "abort"))
        self.assertNotIn("runner interrupted", json.dumps(ledger))

    def test_timeout_cleanup_is_bounded_terminal_and_classified(self) -> None:
        candidate = self._candidate_module()
        ledger = []
        effects = RecordingCandidateEffects(ledger=ledger)
        workflow = RecordingHostedWorkflow(ledger=ledger)

        def timeout(*args, **kwargs):
            raise TimeoutError("protected-timeout-canary")

        workflow.execute_to_completion = timeout
        with self._admission_bridge(candidate):
            with self.assertRaisesRegex(candidate.CandidateTopologyError, WORKFLOW_ERROR) as caught:
                candidate.run_candidate_topology(
                    exact_assembly(),
                    inspection=exact_inspection(),
                    workflow=workflow,
                    effects=effects,
                )

        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(ledger[-1], ("cleanup", "timeout"))
        self.assertNotIn("protected-timeout-canary", str(caught.exception))

    def test_report_is_complete_hash_addressed_and_redaction_checked(self) -> None:
        report, _, _, _ = self._run_candidate()

        self.assertEqual(
            [stage["name"] for stage in report["stages"]],
            ["admission", "build", "workflow", "hello", "empty-successor", "cleanup"],
        )
        self.assertTrue(all(set(stage) == {"name", "started_at", "ended_at", "result"} for stage in report["stages"]))
        self.assertIsNone(report["first_failed_stage"])
        self.assertEqual(report["assembly_sha256"], canonical_sha256(exact_assembly()))
        self.assertEqual(
            report["report_sha256"],
            canonical_report_sha256(report),
        )
        self.assertTrue(report["redaction_verified"])
        self.assertEqual(report["protected_material_retained"], False)
        rendered = json.dumps(report, sort_keys=True).lower()
        for forbidden in ("password", "credential-value", "plaintext", "ciphertext"):
            self.assertNotIn(forbidden, rendered)

    def test_candidate_measurements_are_dynamic_exact_and_precede_docker_mutation(self) -> None:
        candidate = self._candidate_module()
        assembly = exact_assembly()
        inspection = exact_inspection()
        dynamic_commit = "0123456789abcdef" * 2 + "01234567"
        dynamic_tree = "89abcdef01234567" * 2 + "89abcdef"
        dynamic_hashes = {
            "products/cpk_server/Dockerfile": "1" * 64,
            "acceptance/candidate_topology/Dockerfile": "2" * 64,
            "dist/control_plane_kit_core.whl": "3" * 64,
            "dist/control_plane_kit_operations.whl": "4" * 64,
        }
        dynamic_base = "sha256:" + "5" * 64
        for owner in ("server_source", "runner"):
            assembly[owner]["commit"] = dynamic_commit
            assembly[owner]["tree"] = dynamic_tree
        inspection["server_source"] = {
            "commit": dynamic_commit,
            "tree": dynamic_tree,
            "clean": True,
        }
        inspection["files"] = dynamic_hashes
        inspection["images"] = {"cpk_server_base": dynamic_base}
        client = RecordingDockerClient()
        effects = self._docker_effects(candidate, client)

        escaped = None
        admitted = None
        try:
            admitted = candidate.admit_candidate_assembly(assembly, inspection)
        except candidate.CandidateAssemblyError as error:
            escaped = error

        with self.subTest(boundary="dynamic-relational-admission"):
            self.assertIsNone(escaped)
            if escaped is None:
                self.assertIs(admitted, assembly)
        with self.subTest(boundary="exact-sha-shapes"):
            self.assertTrue(
                all(
                    len(value) == 40
                    and value == value.lower()
                    and set(value) <= set("0123456789abcdef")
                    for value in (dynamic_commit, dynamic_tree)
                )
            )
            self.assertTrue(
                all(
                    len(value) == 64
                    and value == value.lower()
                    and set(value) <= set("0123456789abcdef")
                    for value in (
                        *dynamic_hashes.values(),
                        dynamic_base.removeprefix("sha256:"),
                    )
                )
            )
        with self.subTest(boundary="measurement-before-docker"):
            self.assertEqual(client.ledger, [])
        source = inspect.getsource(candidate)
        with self.subTest(boundary="no-placeholder-measurements"):
            for placeholder in (
                'RUNNER_COMMIT = "fc46e42',
                'RUNNER_TREE = "eeab26c6',
                'OVERLAY_SHA256 = "c" * 64',
                'CORE_WHEEL_SHA256 = "d" * 64',
                'OPERATIONS_WHEEL_SHA256 = "e" * 64',
                'CPK_SERVER_BASE_IMAGE = "sha256:" + "9" * 64',
            ):
                self.assertNotIn(placeholder, source)

    def test_docker_effects_start_one_pinned_postgres_and_supply_four_ephemeral_dsns(self) -> None:
        candidate = self._candidate_module()
        client = RecordingDockerClient()
        effects = self._docker_effects(candidate, client)
        postgres_name = effects._name("postgres")
        environment = {
            **CANDIDATE_SERVER_ENVIRONMENT,
            **{
                name: value.replace("candidate-postgres", postgres_name)
                for name, value in POSTGRES_DSN_ENVIRONMENT.items()
            },
        }
        effects.preflight_inventory(exact_assembly())
        effects.build_candidate_image(
            exact_assembly(),
            base_image=CPK_SERVER_BASE_IMAGE,
        )
        with patch.dict(candidate.os.environ, environment, clear=True):
            effects.start_candidate_server(CANDIDATE_IMAGE_ID)

        runs = client.container_runs
        postgres = [value for value in runs if value["image"] == POSTGRES_IMAGE]
        server = [value for value in runs if value["image"] == CANDIDATE_IMAGE_ID]
        readiness = [
            value
            for name, value in client.ledger
            if name == "container-exec" and "pg_isready" in repr(value)
        ]
        with self.subTest(boundary="one-pinned-postgres"):
            self.assertEqual(len(postgres), 1)
            if postgres:
                self.assertEqual(postgres[0]["name"], postgres_name)
                self.assertEqual(postgres[0]["network"], effects._name("runtime"))
                self.assertEqual(postgres[0]["labels"], CANDIDATE_LABELS)
                self.assertEqual(
                    postgres[0]["environment"],
                    POSTGRES_BOOTSTRAP_ENVIRONMENT,
                )
        with self.subTest(boundary="non-sql-readiness"):
            self.assertEqual(
                readiness,
                [
                    (
                        postgres_name,
                        (
                            "pg_isready",
                            "-U",
                            POSTGRES_USER,
                            "-d",
                            POSTGRES_DB,
                        ),
                    )
                ],
            )
            self.assertNotIn("psql", repr(readiness).lower())
            self.assertNotIn("select ", repr(readiness).lower())
            cleanup = effects.cleanup(reason="evidence")
            report = candidate._base_report(
                exact_assembly(),
                cleanup=cleanup,
                first_failed_stage=None,
                status="passed",
            )
            for evidence in (
                json.dumps(report, sort_keys=True),
                repr(client.ledger),
                str(candidate.CandidateTopologyError(WORKFLOW_ERROR)),
            ):
                self.assertNotIn(POSTGRES_PASSWORD, evidence)
        with self.subTest(boundary="four-explicit-dsns"):
            self.assertEqual(len(server), 1)
            if server:
                self.assertEqual(
                    {
                        name: server[0]["environment"].get(name)
                        for name in POSTGRES_DSN_ENVIRONMENT
                    },
                    {
                        name: value.replace("candidate-postgres", postgres_name)
                        for name, value in POSTGRES_DSN_ENVIRONMENT.items()
                    },
                )

    def test_postgres_readiness_retries_are_bounded_before_server_start(self) -> None:
        candidate = self._candidate_module()
        client = RecordingDockerClient()
        client.postgres_readiness[:] = [1, 1, 0]
        effects = self._docker_effects(candidate, client)
        delays = []
        escaped = None
        effects.preflight_inventory(exact_assembly())
        effects.build_candidate_image(
            exact_assembly(),
            base_image=CPK_SERVER_BASE_IMAGE,
        )
        with patch.dict(candidate.os.environ, CANDIDATE_SERVER_ENVIRONMENT, clear=True):
            with patch.object(
                candidate.os,
                "stat",
                return_value=SimpleNamespace(
                    st_gid=DOCKER_SOCKET_GID,
                    st_mode=stat.S_IFSOCK,
                ),
            ):
                with patch.object(
                    candidate,
                    "_sleep",
                    new=delays.append,
                    create=True,
                ):
                    try:
                        effects.start_candidate_server(CANDIDATE_IMAGE_ID)
                    except BaseException as error:
                        escaped = error

        readiness = tuple(
            value
            for name, value in client.ledger
            if name == "container-exec" and "pg_isready" in repr(value)
        )
        with self.subTest(boundary="bounded-readiness-attempts"):
            self.assertEqual(len(readiness), POSTGRES_READY_ATTEMPTS)
        with self.subTest(boundary="bounded-readiness-delays"):
            self.assertEqual(
                tuple(delays),
                (POSTGRES_READY_RETRY_SECONDS,) * (POSTGRES_READY_ATTEMPTS - 1),
            )
        with self.subTest(boundary="eventual-readiness-succeeds"):
            self.assertIsNone(escaped)
        with self.subTest(boundary="server-starts-only-after-readiness"):
            server_runs = tuple(
                value
                for value in client.container_runs
                if value["image"] == CANDIDATE_IMAGE_ID
            )
            self.assertEqual(len(server_runs), 1)
            if server_runs:
                last_ready = max(
                    index
                    for index, (name, value) in enumerate(client.ledger)
                    if name == "container-exec" and "pg_isready" in repr(value)
                )
                server_run = next(
                    index
                    for index, (name, value) in enumerate(client.ledger)
                    if name == "container-run"
                    and value["image"] == CANDIDATE_IMAGE_ID
                )
                self.assertLess(last_ready, server_run)

    def test_postgres_readiness_exhaustion_cleans_and_publishes_failed_report(self) -> None:
        candidate = self._candidate_module()
        client = RecordingDockerClient()
        client.postgres_readiness[:] = [1] * POSTGRES_READY_ATTEMPTS
        docker_module = SimpleNamespace(from_env=lambda: client)
        delays = []
        escaped = None
        report = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assembly_path = root / "candidate-assembly.json"
            inspection_path = root / "candidate-inspection.json"
            report_path = root / "candidate-topology-report.json"
            assembly_path.write_text(
                json.dumps(exact_assembly(), sort_keys=True),
                encoding="utf-8",
            )
            inspection_path.write_text(
                json.dumps(exact_inspection(), sort_keys=True),
                encoding="utf-8",
            )
            argv = [
                "--assembly",
                str(assembly_path),
                "--inspection",
                str(inspection_path),
                "--report",
                str(report_path),
                "--project-label",
                "org.openj92.project=control-plane-kit-servers",
                "--scenario-label",
                "org.openj92.cpk.scenario=candidate-topology-1714",
            ]
            with patch.dict(sys.modules, {"docker": docker_module}):
                with patch.dict(
                    candidate.os.environ,
                    CANDIDATE_SERVER_ENVIRONMENT,
                    clear=True,
                ):
                    with patch.object(
                        candidate.os,
                        "stat",
                        return_value=SimpleNamespace(
                            st_gid=DOCKER_SOCKET_GID,
                            st_mode=stat.S_IFSOCK,
                        ),
                    ):
                        with patch.object(
                            candidate,
                            "_sleep",
                            new=delays.append,
                            create=True,
                        ):
                            try:
                                candidate.main(
                                    argv,
                                    workflow_factory=lambda *args, **kwargs: None,
                                    effects_factory=lambda **kwargs: candidate.DockerCandidateEffects(
                                        **kwargs
                                    ),
                                )
                            except BaseException as error:
                                escaped = error
            if report_path.is_file():
                report = json.loads(report_path.read_text(encoding="utf-8"))

        readiness = tuple(
            value
            for name, value in client.ledger
            if name == "container-exec" and "pg_isready" in repr(value)
        )
        with self.subTest(boundary="exhausted-fixed-error"):
            self.assertIs(type(escaped), candidate.CandidateTopologyError)
            if type(escaped) is candidate.CandidateTopologyError:
                self.assertEqual(str(escaped), WORKFLOW_ERROR)
                self.assertIsNone(escaped.__cause__)
                self.assertIsNone(escaped.__context__)
        with self.subTest(boundary="exhausted-bounded-attempts"):
            self.assertEqual(len(readiness), POSTGRES_READY_ATTEMPTS)
            self.assertEqual(
                tuple(delays),
                (POSTGRES_READY_RETRY_SECONDS,) * (POSTGRES_READY_ATTEMPTS - 1),
            )
        with self.subTest(boundary="exhaustion-never-starts-server"):
            self.assertFalse(
                any(
                    value["image"] == CANDIDATE_IMAGE_ID
                    for value in client.container_runs
                )
            )
        with self.subTest(boundary="exhaustion-cleans-owned-resources"):
            removed = tuple(
                value
                for name, value in client.ledger
                if name in {"container-remove", "network-remove", "image-remove"}
            )
            for role in ("postgres", "runtime"):
                self.assertTrue(any(effects_name in repr(removed) for effects_name in (
                    f"-{role}",
                )))
        with self.subTest(boundary="exhaustion-terminal-report"):
            self.assertEqual(report.get("status"), "failed")
            self.assertEqual(report.get("first_failed_stage"), "build")
            self.assertEqual(
                report.get("report_sha256"),
                canonical_report_sha256(report),
            )
            rendered = json.dumps(report, sort_keys=True)
            for protected in (POSTGRES_PASSWORD, "present", "worker-present"):
                self.assertNotIn(protected, rendered)

    def test_candidate_server_environment_socket_and_gid_are_exactly_bounded(self) -> None:
        candidate = self._candidate_module()
        client = RecordingDockerClient()
        effects = self._docker_effects(candidate, client)
        postgres_name = effects._name("postgres")
        expected_environment = {
            **CANDIDATE_SERVER_ENVIRONMENT,
            **{
                name: value.replace("candidate-postgres", postgres_name)
                for name, value in POSTGRES_DSN_ENVIRONMENT.items()
            },
        }
        hostile_environment = {
            **expected_environment,
            "CPK_UNRELATED_HOST_SECRET": "must-not-cross-boundary",
            "HOME": "/protected-host-home",
        }
        effects.preflight_inventory(exact_assembly())
        effects.build_candidate_image(exact_assembly(), base_image=CPK_SERVER_BASE_IMAGE)

        def observed_socket(path):
            client.ledger.append(("socket-stat", path))
            return SimpleNamespace(st_gid=DOCKER_SOCKET_GID, st_mode=stat.S_IFSOCK)

        with patch.dict(candidate.os.environ, hostile_environment, clear=True):
            with patch.object(
                candidate.os,
                "stat",
                side_effect=observed_socket,
            ):
                effects.start_candidate_server(CANDIDATE_IMAGE_ID)

        server = next(
            (
                value
                for value in client.container_runs
                if value["image"] == CANDIDATE_IMAGE_ID
            ),
            {},
        )
        with self.subTest(boundary="closed-environment"):
            self.assertEqual(server.get("environment"), expected_environment)
        with self.subTest(boundary="docker-socket-only"):
            self.assertEqual(
                server.get("volumes"),
                {
                    "/var/run/docker.sock": {
                        "bind": "/var/run/docker.sock",
                        "mode": "rw",
                    }
                },
            )
        with self.subTest(boundary="exact-socket-gid"):
            self.assertEqual(
                tuple(str(value) for value in server.get("group_add", ())),
                (str(DOCKER_SOCKET_GID),),
            )
        with self.subTest(boundary="socket-admission-precedes-docker-mutation"):
            socket_position = client.ledger.index(
                ("socket-stat", "/var/run/docker.sock")
            )
            mutation_position = next(
                index
                for index, (name, _) in enumerate(client.ledger)
                if name in {"network-create", "container-run"}
            )
            self.assertLess(socket_position, mutation_position)
        with self.subTest(boundary="no-arbitrary-host-forwarding"):
            self.assertNotIn("CPK_UNRELATED_HOST_SECRET", server.get("environment", {}))
            self.assertNotIn("must-not-cross-boundary", repr(server))

    def test_candidate_server_constructs_owned_dsns_and_exact_bearer_principals(self) -> None:
        candidate = self._candidate_module()
        client = RecordingDockerClient()
        effects = self._docker_effects(candidate, client)
        postgres_name = effects._name("postgres")
        expected_principals = [
            {
                "credential": "present",
                "subject_id": "hosted-operator",
                "kind": "operator",
                "workspace_grants": {WORKSPACE_ID: list(OPERATOR_SCOPES)},
            },
            {
                "credential": "worker-present",
                "subject_id": "candidate-worker",
                "kind": "worker",
                "workspace_grants": {WORKSPACE_ID: list(WORKER_SCOPES)},
            },
        ]
        expected_dsns = {
            name: (
                f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
                f"{postgres_name}:5432/{POSTGRES_DB}"
            )
            for name in (
                "CPK_WORKPLACE_DATABASE_URL",
                "CPK_ACTIVITY_HISTORY_DATABASE_URL",
                "CPK_OBSERVER_STATE_DATABASE_URL",
                "CPK_GRAPH_TOPOLOGY_DATABASE_URL",
            )
        }
        expected_environment = {
            "CPK_SERVER_MODE": "execution-capable",
            "CPK_CONTROL_AUTH_VERIFIER": "static-development",
            "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON": json.dumps(
                expected_principals,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "CPK_PORT": "8080",
            "CPK_RUNTIME_INTERPRETERS": "docker",
            "CPK_INGRESS_INTERPRETERS": "none",
            "CPK_PRODUCT_MATERIAL_RESOLVER": "none",
            **expected_dsns,
        }
        hostile_host_environment = {
            name: f"hostile-owned-value-{index}"
            for index, name in enumerate(expected_environment)
        }
        hostile_host_environment.update(
            {
                "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON": (
                    '{"hostile-principal":"must-not-cross-boundary"}'
                ),
                "CPK_UNRELATED_HOST_SECRET": "must-not-cross-boundary",
            }
        )
        hostile_values = tuple(hostile_host_environment.values())
        effects.preflight_inventory(exact_assembly())
        effects.build_candidate_image(exact_assembly(), base_image=CPK_SERVER_BASE_IMAGE)
        with patch.dict(candidate.os.environ, hostile_host_environment, clear=True):
            with patch.object(
                candidate.os,
                "stat",
                return_value=SimpleNamespace(
                    st_gid=DOCKER_SOCKET_GID,
                    st_mode=stat.S_IFSOCK,
                ),
            ):
                effects.start_candidate_server(CANDIDATE_IMAGE_ID)

        server = next(
            value
            for value in client.container_runs
            if value["image"] == CANDIDATE_IMAGE_ID
        )
        observed_environment = server.get("environment")
        principal_text = (
            observed_environment.get("CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON")
            if type(observed_environment) is dict
            else None
        )
        parsed_principals = None
        if type(principal_text) is str:
            try:
                candidate_principals = json.loads(principal_text)
            except json.JSONDecodeError as error:
                parsed_principals = error
            else:
                if type(candidate_principals) is list:
                    parsed_principals = candidate_principals
        observed_operator = None
        observed_worker = None
        if type(parsed_principals) is list and len(parsed_principals) >= 2:
            observed_operator, observed_worker = parsed_principals[:2]
        with self.subTest(boundary="owned-postgres-dsns"):
            self.assertEqual(observed_environment, expected_environment)
            self.assertEqual(
                set(observed_environment) if type(observed_environment) is dict else set(),
                set(expected_environment),
            )
            for value in expected_dsns.values():
                self.assertIn(postgres_name, value)
            for hostile_value in hostile_values:
                observed_values = (
                    observed_environment.values()
                    if type(observed_environment) is dict
                    else ()
                )
                self.assertNotIn(hostile_value, observed_values)
        with self.subTest(boundary="operator-bearer-and-scopes"):
            self.assertEqual(observed_operator, expected_principals[0])
        with self.subTest(boundary="worker-bearer-and-scopes"):
            self.assertEqual(observed_worker, expected_principals[1])
        with self.subTest(boundary="bearers-redacted-from-evidence"):
            cleanup = effects.cleanup(reason="evidence")
            report = candidate._base_report(
                exact_assembly(),
                cleanup=cleanup,
                first_failed_stage=None,
                status="passed",
            )
            for rendered in (json.dumps(report, sort_keys=True), repr(client.ledger)):
                for protected in (
                    "present",
                    "worker-present",
                    POSTGRES_PASSWORD,
                    *hostile_values,
                ):
                    self.assertNotIn(protected, rendered)

    def test_missing_or_non_socket_docker_endpoint_fails_before_mutation(self) -> None:
        candidate = self._candidate_module()
        rows = (
            ("missing", FileNotFoundError("protected-missing-socket")),
            (
                "non-socket",
                SimpleNamespace(
                    st_gid=DOCKER_SOCKET_GID,
                    st_mode=stat.S_IFREG,
                ),
            ),
        )
        for name, observed in rows:
            client = RecordingDockerClient()
            effects = self._docker_effects(candidate, client)
            effects.preflight_inventory(exact_assembly())
            effects.build_candidate_image(
                exact_assembly(),
                base_image=CPK_SERVER_BASE_IMAGE,
            )
            before_start = len(client.ledger)
            escaped = None
            with patch.dict(
                candidate.os.environ,
                CANDIDATE_SERVER_ENVIRONMENT,
                clear=True,
            ):
                with patch.object(
                    candidate.os,
                    "stat",
                    side_effect=(observed if type(observed) is FileNotFoundError else None),
                    return_value=(
                        observed if type(observed) is SimpleNamespace else None
                    ),
                ):
                    try:
                        effects.start_candidate_server(CANDIDATE_IMAGE_ID)
                    except BaseException as error:
                        escaped = error

            mutation = tuple(
                value
                for event, value in client.ledger[before_start:]
                if event in {"network-create", "container-run"}
            )
            with self.subTest(name=name, boundary="fixed-error"):
                self.assertIs(type(escaped), candidate.CandidateTopologyError)
                if type(escaped) is candidate.CandidateTopologyError:
                    self.assertEqual(str(escaped), WORKFLOW_ERROR)
                    self.assertIsNone(escaped.__cause__)
                    self.assertIsNone(escaped.__context__)
            with self.subTest(name=name, boundary="zero-docker-mutation"):
                self.assertEqual(mutation, ())
            with self.subTest(name=name, boundary="protected-detail-redacted"):
                self.assertNotIn("protected-missing-socket", str(escaped))

    def test_probe_resolves_hello_runtime_container_network_endpoint_and_image(self) -> None:
        candidate = self._candidate_module()
        client = RecordingDockerClient()
        effects = self._docker_effects(candidate, client)
        effects.preflight_inventory(exact_assembly())
        effects.build_candidate_image(exact_assembly(), base_image=CPK_SERVER_BASE_IMAGE)
        with patch.dict(candidate.os.environ, CANDIDATE_SERVER_ENVIRONMENT, clear=True):
            effects.start_candidate_server(CANDIDATE_IMAGE_ID)
        hello_container, hello_network = client.seed_hello_runtime()

        result = effects.probe_hello(labelled=True, attach_runtime_network=True)
        probe_run = next(
            value
            for value in client.container_runs
            if value["image"] == CURL_IMAGE
        )
        connections = [value for name, value in client.ledger if name == "network-connect"]
        probe_exec = [
            value
            for name, value in client.ledger
            if name == "container-exec" and value[0] == probe_run["name"]
        ]
        with self.subTest(boundary="labelled-independent-probe"):
            self.assertEqual(probe_run["labels"], CANDIDATE_LABELS)
            self.assertEqual(probe_run["network_mode"], "none")
        with self.subTest(boundary="provider-runtime-network-only"):
            self.assertEqual(connections, [(hello_network.name, probe_run["name"])])
        with self.subTest(boundary="graph-derived-provider-endpoint"):
            self.assertEqual(
                probe_exec,
                [
                    (
                        probe_run["name"],
                        (
                            "curl",
                            "--fail",
                            "--silent",
                            f"http://{hello_container.name}:8080/",
                        ),
                    )
                ],
            )
        with self.subTest(boundary="published-provider-image-attestation"):
            self.assertEqual(hello_container.image.id, HELLO_LOCAL_IMAGE_ID)
            self.assertEqual(
                hello_container.attrs["Config"]["Image"],
                HELLO_IMAGE,
            )
            self.assertEqual(
                tuple(hello_container.image.attrs["RepoDigests"]),
                (HELLO_IMAGE,),
            )
            self.assertEqual(result.get("target_image_id"), HELLO_LOCAL_IMAGE_ID)
            self.assertEqual(result.get("target_image_reference"), HELLO_IMAGE)
            self.assertEqual(result.get("response"), HELLO_RESPONSE)

    def test_preflight_and_cleanup_own_every_candidate_resource_and_preserve_foreign_truth(
        self,
    ) -> None:
        candidate = self._candidate_module()
        client = RecordingDockerClient()
        client.seed_foreign_canary()
        effects = self._docker_effects(candidate, client)
        roles = ("server", "probe", "postgres")
        for role in roles:
            name = effects._name(role)
            client.containers.values.append(
                RecordingDockerContainer(
                    client=client,
                    image_reference=CANDIDATE_IMAGE_ID,
                    name=name,
                    identifier="sha256:" + hashlib.sha256(name.encode("ascii")).hexdigest(),
                    labels=CANDIDATE_LABELS,
                )
            )
        runtime_name = effects._name("runtime")
        client.networks.values.append(
            RecordingDockerNetwork(
                client=client,
                name=runtime_name,
                labels=CANDIDATE_LABELS,
            )
        )
        candidate_tag = effects._name("candidate") + ":latest"
        client.images.values.append(
            RecordingDockerImage("sha256:" + "4" * 64, (candidate_tag,))
        )

        observed = effects.preflight_inventory(exact_assembly())
        expected_collisions = {
            ("container", effects._name(role)) for role in roles
        }
        expected_collisions.update(
            {
                ("network", runtime_name),
                ("image", candidate_tag),
            }
        )
        with self.subTest(boundary="complete-pre-mutation-collisions"):
            self.assertEqual(set(observed["collisions"]), expected_collisions)
        with self.subTest(boundary="zero-docker-mutation"):
            self.assertFalse(
                any(
                    name in {"image-build", "network-create", "container-run"}
                    for name, _ in client.ledger
                )
            )
        with self.subTest(boundary="foreign-canary-is-observed-not-declared"):
            self.assertIn("foreign-container-1714", observed["inventory"]["containers"])
            self.assertIn("foreign-network-1714", observed["inventory"]["networks"])
            foreign_build_tags = tuple(
                tag
                for image in client.images.list()
                for tag in image.tags
                if tag == "foreign-build-1714:latest"
            )
            self.assertEqual(foreign_build_tags, ("foreign-build-1714:latest",))
            self.assertEqual(
                observed["inventory"]["build_residue"],
                foreign_build_tags,
            )
            self.assertIn("sha256:" + "3" * 64, observed["inventory"]["images"])

        cleanup_client = RecordingDockerClient()
        cleanup_client.seed_foreign_canary()
        cleanup_effects = self._docker_effects(candidate, cleanup_client)
        cleanup_effects.preflight_inventory(exact_assembly())
        cleanup_effects.build_candidate_image(
            exact_assembly(),
            base_image=CPK_SERVER_BASE_IMAGE,
        )
        cleanup_postgres_name = cleanup_effects._name("postgres")
        cleanup_environment = {
            **CANDIDATE_SERVER_ENVIRONMENT,
            **{
                name: value.replace("candidate-postgres", cleanup_postgres_name)
                for name, value in POSTGRES_DSN_ENVIRONMENT.items()
            },
        }
        with patch.dict(candidate.os.environ, cleanup_environment, clear=True):
            cleanup_effects.start_candidate_server(CANDIDATE_IMAGE_ID)
        cleanup_result = cleanup_effects.cleanup(reason="success")
        with self.subTest(boundary="tracked-owned-resources-removed"):
            builds = tuple(
                value for name, value in cleanup_client.ledger if name == "image-build"
            )
            self.assertEqual(
                tuple(value["tag"] for value in builds),
                (cleanup_effects._name("candidate") + ":latest",),
            )
            removed = tuple(
                value
                for name, value in cleanup_client.ledger
                if name in {"container-remove", "network-remove", "image-remove"}
            )
            for role in ("server", "postgres", "runtime"):
                self.assertTrue(
                    any(cleanup_effects._name(role) in repr(value) for value in removed)
                )
            self.assertTrue(any(CANDIDATE_IMAGE_ID in repr(value) for value in removed))
        with self.subTest(boundary="exact-allowed-post-inventory"):
            self.assertEqual(
                cleanup_result["post_inventory"],
                {
                    "containers": ("foreign-container-1714",),
                    "networks": ("foreign-network-1714",),
                    "volumes": (),
                    "images": (
                        "sha256:" + "3" * 64,
                        "sha256:" + "8" * 64,
                        CPK_SERVER_BASE_IMAGE,
                    ),
                    "build_residue": ("foreign-build-1714:latest",),
                    "postgres_relations": (),
                },
            )
            post_tags = {
                tag
                for image in cleanup_client.images.list()
                for tag in image.tags
            }
            self.assertIn("foreign-build-1714:latest", post_tags)
            self.assertNotIn(
                cleanup_effects._name("candidate") + ":latest",
                post_tags,
            )
        with self.subTest(boundary="foreign-resources-byte-preserved"):
            self.assertEqual(
                tuple(
                    value
                    for name, value in cleanup_client.ledger
                    if name in {"container-remove", "network-remove", "image-remove"}
                    and "foreign" in repr(value)
                ),
                (),
            )

        residue_client = RecordingDockerClient()
        residue_client.seed_foreign_canary()
        residue_effects = self._docker_effects(candidate, residue_client)
        residue_effects.preflight_inventory(exact_assembly())
        residue_effects.build_candidate_image(
            exact_assembly(),
            base_image=CPK_SERVER_BASE_IMAGE,
        )
        with patch.dict(candidate.os.environ, CANDIDATE_SERVER_ENVIRONMENT, clear=True):
            residue_effects.start_candidate_server(CANDIDATE_IMAGE_ID)
        provider_container, provider_network = residue_client.seed_hello_runtime()
        residue_error = None
        try:
            residue_effects.cleanup(reason="success")
        except candidate.CandidateTopologyError as error:
            residue_error = error
        with self.subTest(boundary="provider-runtime-residue-fails"):
            self.assertIs(type(residue_error), candidate.CandidateTopologyError)
            if type(residue_error) is candidate.CandidateTopologyError:
                self.assertEqual(str(residue_error), WORKFLOW_ERROR)
                self.assertIsNone(residue_error.__cause__)
                self.assertIsNone(residue_error.__context__)
            self.assertFalse(provider_container.removed)
            self.assertFalse(provider_network.removed)

    def test_cleanup_filters_runtime_network_residue_by_exact_workspace(self) -> None:
        candidate = self._candidate_module()
        client = RecordingDockerClient()
        foreign_network = client.seed_foreign_workspace_runtime()
        effects = self._docker_effects(candidate, client)
        effects.preflight_inventory(exact_assembly())
        effects.build_candidate_image(
            exact_assembly(),
            base_image=CPK_SERVER_BASE_IMAGE,
        )
        with patch.dict(candidate.os.environ, CANDIDATE_SERVER_ENVIRONMENT, clear=True):
            with patch.object(
                candidate.os,
                "stat",
                return_value=SimpleNamespace(
                    st_gid=DOCKER_SOCKET_GID,
                    st_mode=stat.S_IFSOCK,
                ),
            ):
                effects.start_candidate_server(CANDIDATE_IMAGE_ID)
        escaped = None
        cleanup = {}
        try:
            cleanup = effects.cleanup(reason="success")
        except BaseException as error:
            escaped = error

        with self.subTest(boundary="foreign-workspace-does-not-fail-cleanup"):
            self.assertIsNone(escaped)
        with self.subTest(boundary="foreign-workspace-network-is-preserved"):
            self.assertFalse(foreign_network.removed)
            self.assertIn(
                foreign_network.name,
                cleanup.get("post_inventory", {}).get("networks", ()),
            )
        with self.subTest(boundary="foreign-workspace-network-is-never-removed"):
            self.assertFalse(
                any(
                    event == "network-remove" and value == foreign_network.name
                    for event, value in client.ledger
                )
            )

    def test_cleanup_failure_preserves_original_stage_terminal_report_and_foreign_resources(
        self,
    ) -> None:
        candidate = self._candidate_module()
        client = RecordingDockerClient()
        client.seed_foreign_canary()
        effects = self._docker_effects(candidate, client)
        effects.preflight_inventory(exact_assembly())
        effects.build_candidate_image(exact_assembly(), base_image=CPK_SERVER_BASE_IMAGE)
        with patch.dict(candidate.os.environ, CANDIDATE_SERVER_ENVIRONMENT, clear=True):
            effects.start_candidate_server(CANDIDATE_IMAGE_ID)
        original = RuntimeError("protected-original-probe-failure")
        cleanup_error = RuntimeError("protected-cleanup-failure")

        def fail_probe(**kwargs):
            raise original

        def fail_cleanup(**kwargs):
            raise cleanup_error

        effects.probe_hello = fail_probe
        effects.cleanup = fail_cleanup
        escaped = None
        with self._admission_bridge(candidate):
            try:
                candidate.run_candidate_topology(
                    exact_assembly(),
                    inspection=exact_inspection(),
                    workflow=RecordingHostedWorkflow(),
                    effects=effects,
                    prepared={
                        "admitted": exact_assembly(),
                        "preflight": {"inventory": effects._pre_inventory},
                        "build": {
                            "base_image": CPK_SERVER_BASE_IMAGE,
                            "image_id": CANDIDATE_IMAGE_ID,
                        },
                        "server": None,
                        "server_inspection": None,
                    },
                )
            except BaseException as error:
                escaped = error

        report = getattr(escaped, "candidate_terminal_report", {})
        with self.subTest(boundary="original-failure-identity"):
            self.assertIs(escaped, original)
        with self.subTest(boundary="original-first-failed-stage"):
            self.assertEqual(report.get("first_failed_stage"), "probe")
            self.assertEqual(report.get("status"), "failed")
        with self.subTest(boundary="cleanup-failure-is-observed"):
            self.assertEqual(report.get("cleanup", {}).get("status"), "failed")
            self.assertNotIn("protected-cleanup-failure", json.dumps(report, sort_keys=True))
        with self.subTest(boundary="foreign-resources-untouched"):
            self.assertFalse(
                any(
                    name in {"container-remove", "network-remove", "image-remove"}
                    and "foreign" in repr(value)
                    for name, value in client.ledger
                )
            )

    def _run_candidate(self):
        candidate = self._candidate_module()
        ledger = []
        workflow = RecordingHostedWorkflow(ledger=ledger)
        effects = RecordingCandidateEffects(ledger=ledger)
        with self._admission_bridge(candidate):
            report = candidate.run_candidate_topology(
                exact_assembly(),
                inspection=exact_inspection(),
                workflow=workflow,
                effects=effects,
            )
        return report, workflow, effects, ledger

    def _docker_effects(self, candidate, client):
        docker_module = SimpleNamespace(from_env=lambda: client)
        with patch.dict(sys.modules, {"docker": docker_module}):
            return candidate.DockerCandidateEffects(
                root=ROOT,
                labels=dict(CANDIDATE_LABELS),
                evidence_id=CANDIDATE_LABELS["org.openj92.cpk.evidence"],
            )

    def _invoke_main(
        self,
        *,
        collision: bool = False,
        fail_at: str | None = None,
        use_predecessor_bridge: bool = False,
        wrong_hello: bool = False,
    ):
        candidate = self._candidate_module()
        injectable_main = {
            "workflow_factory",
            "effects_factory",
        }.issubset(inspect.signature(candidate.main).parameters)
        ledger = []
        workflow_factory = RecordingHostedWorkflowFactory(
            ledger=ledger,
            fail_at=fail_at,
        )
        effects_factory = RecordingCandidateEffectsFactory(
            ledger=ledger,
            collision=collision,
            fail_at=fail_at,
            wrong_hello=wrong_hello,
        )
        escaped = None
        exit_code = None
        report = None
        bridge = ()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assembly_path = root / "candidate-assembly.json"
            inspection_path = root / "candidate-inspection.json"
            report_path = root / "candidate-topology-report.json"
            assembly_path.write_text(
                json.dumps(exact_assembly(), sort_keys=True),
                encoding="utf-8",
            )
            inspection_path.write_text(
                json.dumps(exact_inspection(), sort_keys=True),
                encoding="utf-8",
            )
            argv = [
                "--assembly",
                str(assembly_path),
                "--inspection",
                str(inspection_path),
                "--report",
                str(report_path),
                "--project-label",
                "org.openj92.project=control-plane-kit-servers",
                "--scenario-label",
                "org.openj92.cpk.scenario=candidate-topology-1714",
            ]
            try:
                if injectable_main:
                    exit_code = candidate.main(
                        argv,
                        workflow_factory=workflow_factory,
                        effects_factory=effects_factory,
                    )
                elif use_predecessor_bridge:
                    legacy_argv = [
                        *argv,
                        "--base-image",
                        CPK_SERVER_BASE_IMAGE,
                        "--foreign-canary",
                        FOREIGN_RESOURCE_CANARY,
                        "--first-failed-stage",
                        "none",
                        "--base-url",
                        "http://candidate-server-container:8080",
                        "--server-container",
                        "candidate-server-container",
                    ]
                    with self._main_predecessor_bridge(
                        candidate,
                        ledger=ledger,
                        workflow_factory=workflow_factory,
                        effects_factory=effects_factory,
                    ) as bridge:
                        exit_code = candidate.main(legacy_argv)
                else:
                    exit_code = candidate.main(argv)
            except BaseException as error:
                escaped = error
            if report_path.is_file():
                report = json.loads(report_path.read_text(encoding="utf-8"))
        effects = effects_factory.instances[0] if effects_factory.instances else None
        return {
            "effects": effects,
            "effects_factory": effects_factory,
            "bridge": bridge,
            "escaped": escaped,
            "exit_code": exit_code,
            "injectable_main": injectable_main,
            "ledger": ledger,
            "report": report,
            "workflow_factory": workflow_factory,
        }

    @contextmanager
    def _main_predecessor_bridge(
        self,
        candidate,
        *,
        ledger,
        workflow_factory,
        effects_factory,
    ):
        bridge = (
            "HostedWorkflow-construction",
            "DockerCandidateEffects-construction",
            "legacy-argv",
            "legacy-admission",
        )
        ledger.append(("predecessor-bridge", bridge))
        with patch.object(candidate, "HostedWorkflow", new=workflow_factory):
            with patch.object(
                candidate,
                "DockerCandidateEffects",
                new=effects_factory,
            ):
                with patch.object(
                    candidate,
                    "admit_candidate_assembly",
                    return_value=exact_assembly(),
                ):
                    yield bridge

    @contextmanager
    def _admission_bridge(self, candidate):
        try:
            candidate.admit_candidate_assembly(
                exact_assembly(),
                exact_inspection(),
            )
        except candidate.CandidateAssemblyError:
            with patch.object(
                candidate,
                "admit_candidate_assembly",
                return_value=exact_assembly(),
            ):
                yield
        else:
            yield

    def _candidate_module(self):
        if importlib.util.find_spec("scripts.cpk_server_candidate_topology") is None:
            self.fail("candidate topology runner is not implemented")
        return importlib.import_module("scripts.cpk_server_candidate_topology")


if __name__ == "__main__":
    unittest.main()
