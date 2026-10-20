"""Closed diagnostics at the existing packaged witness completion boundary."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import packaged_managed_witness as witness


class ManagedWitnessDiagnosticTests(unittest.TestCase):
    def test_only_allowlisted_qualification_reasons_survive(self):
        for failure, reason in (
            (witness.QualificationFailure("native_parent"), "native_parent"),
            (witness.QualificationFailure("PRIVATE_CANDIDATE"), "helper_exception"),
            (RuntimeError("native_parent"), "helper_exception"),
            (RuntimeError("PRIVATE_CANDIDATE"), "helper_exception"),
            (witness.QualificationFailure(["PRIVATE_CANDIDATE"]), "helper_exception"),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(witness.helper_failure_value(failure),
                                 {"outcome": "failure", "reason": reason})

    def test_nonzero_exit_preserves_failure_with_closed_diagnostics(self):
        cases = (
            ({"outcome": "failure", "reason": "native_parent"}, None, "valid_error"),
            (None, FileNotFoundError("PRIVATE_CANDIDATE"), "unavailable"),
            (None, ValueError("PRIVATE_CANDIDATE"), "invalid"),
            ({"outcome": "failure", "reason": "PRIVATE_CANDIDATE"}, None, "invalid"),
            ({"outcome": "failure", "reason": "native_parent",
              "extra": "PRIVATE_CANDIDATE"}, None, "invalid"),
            ({"outcome": "failure", "reason": ["PRIVATE_CANDIDATE"]}, None, "invalid"),
            ({"native_version": "2026.6.1"}, None, "invalid"),
        )
        for value, error, availability in cases:
            with self.subTest(availability=availability):
                output = io.StringIO()
                with patch.object(witness, "read_helper_result", return_value=value,
                                  side_effect=error), redirect_stdout(output):
                    with self.assertRaisesRegex(witness.QualificationFailure,
                                                "^real_native_observation_failed$"):
                        witness.completed_helper("contents", 7, Path("unused"),
                                                 time.monotonic() + 10)
                self.assertEqual(json.loads(output.getvalue()), {
                    "stage": "managed_cloudflared_helper", "mode": "contents",
                    "exit_code": 7, "result": availability,
                    **({"reason": "native_parent"} if availability == "valid_error" else {}),
                })
                self.assertNotIn("PRIVATE_CANDIDATE", output.getvalue())

    def test_exhausted_deadline_preserves_original_failure_without_read(self):
        output = io.StringIO()
        with patch.object(witness.os, "open") as opened, redirect_stdout(output):
            with self.assertRaisesRegex(witness.QualificationFailure,
                                        "^real_native_observation_failed$"):
                witness.completed_helper("identity", 1, Path("unused"),
                                         time.monotonic() - 1)
        opened.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {
            "stage": "managed_cloudflared_helper", "mode": "identity",
            "exit_code": 1, "result": "deadline_exhausted",
        })

    def test_zero_exit_rejects_failure_envelope_and_preserves_success_payload(self):
        for mode, payload in (
            ("starting", None), ("identity", [1, 1, "42"]),
            ("management", {"pending": True, "identity": [1, 1, "42"]}),
            ("contents", {"native_version": "2026.6.1"}),
        ):
            with self.subTest(mode=mode):
                with patch.object(witness, "read_helper_result", return_value=payload):
                    self.assertIs(witness.completed_helper(
                        mode, 0, Path("unused"), time.monotonic() + 10), payload)
                with patch.object(witness, "read_helper_result", return_value={
                    "outcome": "failure", "reason": "native_parent",
                }):
                    with self.assertRaisesRegex(witness.QualificationFailure,
                                                "^helper_failure_with_zero_exit$"):
                        witness.completed_helper(mode, 0, Path("unused"),
                                                 time.monotonic() + 10)

    def test_failure_record_is_restricted_to_observation_modes_and_best_effort(self):
        failure = RuntimeError("PRIVATE_CANDIDATE")
        with patch.object(witness, "emit_helper") as emit:
            for mode in ("controlled", "fatal", "controller", None):
                self.assertFalse(witness.retain_helper_failure(mode, failure))
            emit.assert_not_called()
            for mode in witness.OBSERVATION_MODES:
                self.assertTrue(witness.retain_helper_failure(mode, failure))
            self.assertEqual(emit.call_count, 4)
            for call in emit.call_args_list:
                self.assertEqual(call.args, (
                    {"outcome": "failure", "reason": "helper_exception"},))
        output = io.StringIO()
        with patch.object(witness, "emit_helper", side_effect=OSError("PRIVATE_CANDIDATE")), \
                redirect_stdout(output), redirect_stderr(output):
            self.assertFalse(witness.retain_helper_failure("contents", failure))
        self.assertEqual(output.getvalue(), "")
