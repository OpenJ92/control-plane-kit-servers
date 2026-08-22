from __future__ import annotations

from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path
import unittest

from candidate_topology_fixture import (
    CANDIDATE_COMMIT,
    CANDIDATE_IMAGE_ID,
    CANDIDATE_TREE,
    CPK_SERVER_BASE_IMAGE,
    CORE_WHEEL_SHA256,
    FOREIGN_RESOURCE_CANARY,
    HELLO_DESCRIPTOR_SHA256,
    HELLO_IMAGE,
    HELLO_RESPONSE,
    HELLO_RESPONSE_SHA256,
    INSTALLED_MODULE_PATHS,
    INSTALLED_RECORD_PATHS,
    INTERPRETERS_COMMIT,
    INTERPRETERS_TREE,
    OPERATIONS_WHEEL_SHA256,
    POSTGRES_IMAGE,
    PRODUCTION_DOCKERFILE_SHA256,
    RecordingCandidateEffects,
    RecordingHostedWorkflow,
    SECRETS_COMMIT,
    SECRETS_TREE,
    SERVER_BASELINE_COMMIT,
    SERVER_BASELINE_TREE,
    SNAPSHOT_MANIFEST_SHA256,
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
        rendered = json.dumps(assembly, sort_keys=True).lower()
        for forbidden in ("password", "credential", "plaintext", "ciphertext", "token"):
            self.assertNotIn(forbidden, rendered)

    def test_control_recorders_expose_public_phases_without_runtime_repair(self) -> None:
        ledger = []
        workflow = RecordingHostedWorkflow(ledger=ledger)
        effects = RecordingCandidateEffects(ledger=ledger)

        session_id = workflow.start_session("hello")
        desired_graph_id = workflow.set_desired_graph(session_id=session_id)
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

        admitted = candidate.admit_candidate_assembly(assembly, exact_inspection())

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

    def test_each_evidence_row_has_one_exact_non_promoting_classification(self) -> None:
        candidate = self._candidate_module()
        ledger = []
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

    def _run_candidate(self):
        candidate = self._candidate_module()
        ledger = []
        workflow = RecordingHostedWorkflow(ledger=ledger)
        effects = RecordingCandidateEffects(ledger=ledger)
        report = candidate.run_candidate_topology(
            exact_assembly(),
            inspection=exact_inspection(),
            workflow=workflow,
            effects=effects,
        )
        return report, workflow, effects, ledger

    def _candidate_module(self):
        if importlib.util.find_spec("scripts.cpk_server_candidate_topology") is None:
            self.fail("candidate topology runner is not implemented")
        return importlib.import_module("scripts.cpk_server_candidate_topology")


if __name__ == "__main__":
    unittest.main()
