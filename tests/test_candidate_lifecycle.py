from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "scripts.cpk_server_candidate_lifecycle"
PROJECT_LABEL = "org.openj92.project=control-plane-kit-servers"
SCENARIO_LABEL = "org.openj92.cpk.scenario=candidate-topology-1714"
EVIDENCE_ID = "candidate-lifecycle-test"
LABELS = {
    "org.openj92.project": "control-plane-kit-servers",
    "org.openj92.cpk.scenario": "candidate-topology-1714",
    "org.openj92.cpk.evidence": EVIDENCE_ID,
}


class FakeNotFound(Exception):
    pass


class FakeResource:
    def __init__(
        self,
        *,
        identifier: str,
        labels: dict[str, str],
        tags: tuple[str, ...] = (),
    ) -> None:
        self.id = identifier
        self.labels = dict(labels)
        self.tags = tags
        self.removed = False
        self.name = ""

    @property
    def attrs(self) -> dict[str, Any]:
        return {
            "Config": {"Labels": dict(self.labels)},
            "Labels": dict(self.labels),
        }

    def remove(self, *, force: bool = False) -> None:
        self.removed = True


class FakeManager:
    def __init__(self) -> None:
        self.values: dict[str, FakeResource] = {}

    def get(self, coordinate: str) -> FakeResource:
        value = self.values.get(coordinate)
        if value is None or value.removed:
            raise FakeNotFound(coordinate)
        return value


class FakeImages(FakeManager):
    def remove(self, coordinate: str, *, force: bool = False) -> None:
        self.get(coordinate).remove(force=force)


class FakeDockerClient:
    def __init__(self) -> None:
        self.containers = FakeManager()
        self.networks = FakeManager()
        self.images = FakeImages()


class CandidateLifecycleTests(unittest.TestCase):
    def _module(self) -> Any:
        spec = importlib.util.find_spec(MODULE_NAME)
        self.assertIsNotNone(
            spec,
            "candidate-specific interrupted-run ledger is not implemented",
        )
        if spec is None:
            return None
        return __import__(MODULE_NAME, fromlist=["*"])

    def test_ledger_is_atomic_closed_hash_verified_and_predeclares_exact_ownership(
        self,
    ) -> None:
        lifecycle = self._module()
        if lifecycle is None:
            return
        client = FakeDockerClient()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger_path = root / "candidate-run-ledger.json"
            ledger = lifecycle.declare_candidate_ledger(
                ledger_path,
                root=root,
                labels=LABELS,
                evidence_id=EVIDENCE_ID,
                client=client,
                not_found_error=FakeNotFound,
            )

            self.assertTrue(ledger_path.is_file())
            self.assertFalse(Path(str(ledger_path) + ".part").exists())
            self.assertEqual(
                set(ledger),
                {
                    "schema",
                    "scenario",
                    "evidence_id",
                    "ownership_labels",
                    "phase",
                    "classification",
                    "resources",
                    "ledger_sha256",
                },
            )
            self.assertEqual(ledger["phase"], "declared")
            self.assertEqual(ledger["classification"], "incomplete")
            self.assertEqual(ledger, lifecycle.load_candidate_ledger(ledger_path))
            self.assertEqual(
                tuple((row["kind"], row["role"]) for row in ledger["resources"]),
                (
                    ("container", "server"),
                    ("container", "probe"),
                    ("container", "postgres"),
                    ("network", "runtime"),
                    ("image", "candidate"),
                    ("path", "core-wheel"),
                    ("path", "operations-wheel"),
                    ("path", "rfc8785-wheel"),
                ),
            )
            for row in ledger["resources"]:
                self.assertEqual(
                    set(row),
                    {"kind", "role", "coordinate", "observed_id", "disposition"},
                )
                self.assertIsNone(row["observed_id"])
                self.assertEqual(row["disposition"], "declared")

            hostile_documents = []
            extra_top_level = json.loads(json.dumps(ledger))
            extra_top_level["provider_message"] = "registry credential leaked"
            hostile_documents.append(("extra-provider-key", extra_top_level))
            extra_resource_key = json.loads(json.dumps(ledger))
            extra_resource_key["resources"][0]["selector"] = "label=*"
            hostile_documents.append(("broad-selector", extra_resource_key))
            duplicate_identity = json.loads(json.dumps(ledger))
            duplicate_identity["resources"][1]["role"] = "server"
            hostile_documents.append(("duplicate-identity", duplicate_identity))
            sensitive_identity = json.loads(json.dumps(ledger))
            sensitive_identity["evidence_id"] = "password=protected"
            hostile_documents.append(("sensitive-identity", sensitive_identity))
            provider_coordinate = json.loads(json.dumps(ledger))
            provider_coordinate["resources"][0]["coordinate"] = (
                "https://credential@example.invalid/container"
            )
            hostile_documents.append(("provider-coordinate", provider_coordinate))
            for boundary, hostile in hostile_documents:
                with self.subTest(boundary=boundary):
                    ledger_path.write_text(json.dumps(hostile), encoding="utf-8")
                    with self.assertRaises(lifecycle.CandidateLifecycleError):
                        lifecycle.load_candidate_ledger(ledger_path)

    def test_abrupt_barrier_bypasses_in_process_cleanup_and_stays_non_passing(
        self,
    ) -> None:
        lifecycle = self._module()
        if lifecycle is None:
            return
        client = FakeDockerClient()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger_path = root / "candidate-run-ledger.json"
            marker = root / "ordinary-cleanup-ran"
            lifecycle.declare_candidate_ledger(
                ledger_path,
                root=root,
                labels=LABELS,
                evidence_id=EVIDENCE_ID,
                client=client,
                not_found_error=FakeNotFound,
            )
            lifecycle.record_candidate_resource(
                ledger_path,
                kind="image",
                role="candidate",
                observed_id="sha256:" + "a" * 64,
            )
            program = (
                "from pathlib import Path;"
                "from scripts.cpk_server_candidate_lifecycle import "
                "interrupt_candidate_run;"
                f"ledger=Path({str(ledger_path)!r});"
                f"marker=Path({str(marker)!r});"
                "exec(\"try:\\n interrupt_candidate_run(ledger)\\nfinally:"
                "\\n marker.write_text('ordinary cleanup ran')\")"
            )
            completed = subprocess.run(
                [sys.executable, "-c", program],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, lifecycle.INTERRUPTION_EXIT)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(completed.stderr, "")
            self.assertFalse(marker.exists())
            ledger = lifecycle.load_candidate_ledger(ledger_path)
            self.assertEqual(ledger["phase"], "interruption-requested")
            self.assertEqual(ledger["classification"], "interrupted")
            self.assertNotEqual(ledger["classification"], "passed")

            interrupted_bytes = ledger_path.read_bytes()
            with self.assertRaises(lifecycle.CandidateLifecycleError):
                lifecycle.cleanup_candidate_ledger(
                    ledger_path,
                    client=client,
                    classification="passed",
                    not_found_error=FakeNotFound,
                )
            self.assertEqual(ledger_path.read_bytes(), interrupted_bytes)
            self.assertEqual(
                lifecycle.load_candidate_ledger(ledger_path),
                ledger,
            )

    def test_external_cleanup_uses_only_exact_ledger_coordinates_and_is_idempotent(
        self,
    ) -> None:
        lifecycle = self._module()
        if lifecycle is None:
            return
        client = FakeDockerClient()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger_path = root / "candidate-run-ledger.json"
            ledger = lifecycle.declare_candidate_ledger(
                ledger_path,
                root=root,
                labels=LABELS,
                evidence_id=EVIDENCE_ID,
                client=client,
                not_found_error=FakeNotFound,
            )
            candidate = next(
                row for row in ledger["resources"] if row["role"] == "candidate"
            )
            image = FakeResource(
                identifier="sha256:" + "a" * 64,
                labels=LABELS,
                tags=(candidate["coordinate"],),
            )
            client.images.values[candidate["coordinate"]] = image
            lifecycle.record_candidate_resource(
                ledger_path,
                kind="image",
                role="candidate",
                observed_id=image.id,
            )
            original_exit = lifecycle.os._exit
            lifecycle.os._exit = lambda status: (_ for _ in ()).throw(
                SystemExit(status)
            )
            try:
                with self.assertRaisesRegex(SystemExit, str(lifecycle.INTERRUPTION_EXIT)):
                    lifecycle.interrupt_candidate_run(ledger_path)
            finally:
                lifecycle.os._exit = original_exit
            for row in ledger["resources"]:
                if row["kind"] == "path":
                    Path(row["coordinate"]).parent.mkdir(parents=True, exist_ok=True)
                    Path(row["coordinate"]).write_text(row["role"], encoding="utf-8")
            foreign = FakeResource(
                identifier="sha256:" + "f" * 64,
                labels={"foreign": "true"},
                tags=("foreign-image:stable",),
            )
            client.images.values["foreign-image:stable"] = foreign

            first = lifecycle.cleanup_candidate_ledger(
                ledger_path,
                client=client,
                classification="interrupted-contained",
                not_found_error=FakeNotFound,
            )
            second = lifecycle.cleanup_candidate_ledger(
                ledger_path,
                client=client,
                classification="interrupted-contained",
                not_found_error=FakeNotFound,
            )

            self.assertTrue(image.removed)
            self.assertFalse(foreign.removed)
            self.assertEqual(first["classification"], "interrupted-contained")
            self.assertEqual(second, first)
            self.assertTrue(
                all(row["disposition"] in {"removed", "absent"} for row in first["resources"])
            )
            self.assertTrue(
                all(
                    not Path(row["coordinate"]).exists()
                    for row in first["resources"]
                    if row["kind"] == "path"
                )
            )

            terminal_bytes = ledger_path.read_bytes()
            with self.assertRaises(lifecycle.CandidateLifecycleError):
                lifecycle.cleanup_candidate_ledger(
                    ledger_path,
                    client=client,
                    classification="failed-contained",
                    not_found_error=FakeNotFound,
                )
            with self.assertRaises(lifecycle.CandidateLifecycleError):
                lifecycle.record_candidate_resource(
                    ledger_path,
                    kind="image",
                    role="candidate",
                    observed_id=image.id,
                )
            self.assertEqual(ledger_path.read_bytes(), terminal_bytes)

            mismatch_path = root / "mismatch-ledger.json"
            mismatch_client = FakeDockerClient()
            mismatch_evidence_id = "candidate-lifecycle-mismatch"
            mismatch_labels = {
                **LABELS,
                "org.openj92.cpk.evidence": mismatch_evidence_id,
            }
            mismatch = lifecycle.declare_candidate_ledger(
                mismatch_path,
                root=root,
                labels=mismatch_labels,
                evidence_id=mismatch_evidence_id,
                client=mismatch_client,
                not_found_error=FakeNotFound,
            )
            mismatch_image = next(
                row for row in mismatch["resources"] if row["role"] == "candidate"
            )
            wrong = FakeResource(
                identifier="sha256:" + "b" * 64,
                labels={"foreign": "true"},
                tags=(mismatch_image["coordinate"],),
            )
            mismatch_client.images.values[mismatch_image["coordinate"]] = wrong
            with self.assertRaises(lifecycle.CandidateLifecycleError):
                lifecycle.cleanup_candidate_ledger(
                    mismatch_path,
                    client=mismatch_client,
                    classification="interrupted-contained",
                    not_found_error=FakeNotFound,
                )
            self.assertFalse(wrong.removed)

    def test_terminal_classifications_require_exact_preterminal_states(self) -> None:
        lifecycle = self._module()
        if lifecycle is None:
            return
        client = FakeDockerClient()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def declared_ledger(name: str) -> Path:
                evidence_id = f"candidate-lifecycle-{name}"
                path = root / f"{name}.json"
                lifecycle.declare_candidate_ledger(
                    path,
                    root=root / name,
                    labels={
                        **LABELS,
                        "org.openj92.cpk.evidence": evidence_id,
                    },
                    evidence_id=evidence_id,
                    client=client,
                    not_found_error=FakeNotFound,
                )
                return path

            failed_path = declared_ledger("failed")
            failed = lifecycle.cleanup_candidate_ledger(
                failed_path,
                client=client,
                classification="failed-contained",
                not_found_error=FakeNotFound,
            )
            self.assertEqual(failed["phase"], "contained")
            self.assertEqual(failed["classification"], "failed-contained")

            success_path = declared_ledger("success")
            with self.assertRaises(lifecycle.CandidateLifecycleError):
                lifecycle.cleanup_candidate_ledger(
                    success_path,
                    client=client,
                    classification="passed",
                    not_found_error=FakeNotFound,
                )
            with self.assertRaises(lifecycle.CandidateLifecycleError):
                lifecycle.mark_candidate_success(success_path)
            for index, (kind, role) in enumerate(lifecycle.RESOURCE_ROLES[:5]):
                lifecycle.record_candidate_resource(
                    success_path,
                    kind=kind,
                    role=role,
                    observed_id="sha256:" + f"{index + 1:x}" * 64,
                )
            lifecycle.mark_candidate_success(success_path)
            success = lifecycle.cleanup_candidate_ledger(
                success_path,
                client=client,
                classification="passed",
                not_found_error=FakeNotFound,
            )
            self.assertEqual(success["phase"], "passed")
            self.assertEqual(success["classification"], "passed")

            interrupted_path = declared_ledger("interrupted")
            lifecycle.record_candidate_resource(
                interrupted_path,
                kind="image",
                role="candidate",
                observed_id="sha256:" + "c" * 64,
            )
            original_exit = lifecycle.os._exit
            lifecycle.os._exit = lambda status: (_ for _ in ()).throw(
                SystemExit(status)
            )
            try:
                with self.assertRaisesRegex(SystemExit, str(lifecycle.INTERRUPTION_EXIT)):
                    lifecycle.interrupt_candidate_run(interrupted_path)
            finally:
                lifecycle.os._exit = original_exit
            interrupted = lifecycle.cleanup_candidate_ledger(
                interrupted_path,
                client=client,
                classification="interrupted-contained",
                not_found_error=FakeNotFound,
            )
            self.assertEqual(interrupted["phase"], "contained")
            self.assertEqual(
                interrupted["classification"],
                "interrupted-contained",
            )


if __name__ == "__main__":
    unittest.main()
