from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cpk_server_source_live_report import (  # noqa: E402
    SourceLiveInvariantError,
    SourceLivePhase,
    SourceLivePhaseEvidence,
    SourceLivePhaseLedger,
    SourceLiveRunFailed,
    run_source_live_phases,
)


class SourceLivePhaseReportingTests(unittest.TestCase):
    def test_ledger_emits_only_closed_bounded_evidence(self) -> None:
        output = StringIO()
        ledger = SourceLivePhaseLedger(output)

        ledger.succeeded(
            "private-http-a",
            component="cpk-server",
            evidence=SourceLivePhaseEvidence(
                operation_id="operation-a",
                run_id="run-a",
                current_graph_id="graph-a",
                key_id="key-a",
                key_status="active",
                access_path="runtime-private",
                component_health="healthy",
                resource_stage="active",
            ),
        )

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema"], "cpk.source-live-phase")
        self.assertEqual(payload["sequence"], 1)
        self.assertEqual(payload["phase"], "private-http-a")
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["component"], "cpk-server")
        self.assertEqual(payload["evidence"]["access_path"], "runtime-private")
        self.assertNotIn("message", payload)

        for unsafe in (
            "secret://provider/private-key",
            "Bearer operator-token",
            "-----BEGIN PRIVATE KEY-----",
            "line-one\nline-two",
        ):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(ValueError):
                    SourceLivePhaseEvidence(operation_id=unsafe)

    def test_first_failure_skips_later_phases_cleans_once_and_remains_failed(self) -> None:
        output = StringIO()
        ledger = SourceLivePhaseLedger(output)
        calls: list[str] = []

        def fail() -> SourceLivePhaseEvidence:
            calls.append("fail")
            raise SourceLiveInvariantError("gateway-not-ready")

        def forbidden() -> SourceLivePhaseEvidence:
            calls.append("forbidden")
            return SourceLivePhaseEvidence(component_health="healthy")

        def cleanup() -> None:
            calls.append("cleanup")

        with self.assertRaisesRegex(SourceLiveRunFailed, "gateway-not-ready"):
            run_source_live_phases(
                (
                    SourceLivePhase("gateway-ready", "gateway", fail),
                    SourceLivePhase("public-probe", "cpk-server", forbidden),
                ),
                ledger=ledger,
                cleanup=cleanup,
            )

        self.assertEqual(calls, ["fail", "cleanup"])
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(
            [(record["phase"], record["status"]) for record in records],
            [
                ("gateway-ready", "started"),
                ("gateway-ready", "failed"),
                ("public-probe", "skipped"),
                ("abort-cleanup", "started"),
                ("abort-cleanup", "succeeded"),
            ],
        )
        self.assertEqual(records[1]["error_code"], "gateway-not-ready")
        self.assertEqual(records[2]["error_code"], "prior-phase-failed")

    def test_cleanup_failure_is_bounded_and_does_not_replace_primary_failure(self) -> None:
        output = StringIO()
        ledger = SourceLivePhaseLedger(output)

        def fail() -> SourceLivePhaseEvidence:
            raise SourceLiveInvariantError("public-probe-denied")

        def cleanup() -> None:
            raise SourceLiveInvariantError("cleanup-incomplete")

        with self.assertRaises(SourceLiveRunFailed) as raised:
            run_source_live_phases(
                (SourceLivePhase("public-probe", "cpk-server", fail),),
                ledger=ledger,
                cleanup=cleanup,
            )

        self.assertEqual(raised.exception.primary_code, "public-probe-denied")
        self.assertEqual(raised.exception.cleanup_code, "cleanup-incomplete")
        self.assertNotIn("secret", str(raised.exception).lower())


if __name__ == "__main__":
    unittest.main()
