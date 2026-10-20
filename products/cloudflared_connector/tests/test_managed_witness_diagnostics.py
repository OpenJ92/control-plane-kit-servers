"""Closed diagnostics at the existing packaged witness completion boundary."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import packaged_managed_witness as witness


class ManagedWitnessDiagnosticTests(unittest.TestCase):
    def test_stop_profile_resolves_only_reviewed_defaults_or_explicit_integer_ten(self):
        sources = (
            ("28.5.1", "f8215cc266744ef195a50a70d427c345da2acdbb"),
            ("28.0.4", "6430e49a55babd9b8f4d08e70ecb2b68900770fe"),
        )
        cases = [(version, commit, None, source)
                 for version, source in sources for commit in (source, source[:7])]
        cases.append(("unreviewed", "unknown", 10, None))
        for version, commit, timeout, source in cases:
            with self.subTest(version=version, commit=commit, timeout=timeout):
                container = SimpleNamespace(id="controlled", reload=Mock(), attrs={
                    "Config": {"StopSignal": "SIGTERM", "StopTimeout": timeout}})
                client = SimpleNamespace(
                    info=Mock(return_value={"ID": "engine", "OSType": "linux"}),
                    version=Mock(return_value={"Version": version, "GitCommit": commit}))
                with patch("docker.__version__", "7.2.0"), redirect_stdout(io.StringIO()):
                    result = witness.resolve_profile(client, container)
                self.assertEqual(result["stop_timeout"], 10)
                self.assertEqual(result["configured_stop_timeout"], timeout)
                self.assertEqual(result["timeout_origin"],
                                 "container" if timeout is not None else "engine_fixed_default")
                self.assertEqual(result["reviewed_engine_source"], source)
                self.assertEqual(result["engine_commit"], commit)
                container.reload.assert_called_once_with()

    def test_stop_profile_refuses_unknown_mismatched_or_invalid_inputs(self):
        cases = [
            ("unknown", "6430e49", None, "linux", "SIGTERM", "7.2.0", "stop_profile_unproved"),
            ("28.5.1", "6430e49", None, "linux", "SIGTERM", "7.2.0", "stop_profile_unproved"),
            ("28.0.4", "f8215cc", None, "linux", "SIGTERM", "7.2.0", "stop_profile_unproved"),
        ]
        cases += [("28.0.4", commit, None, "linux", "SIGTERM", "7.2.0", "stop_profile_unproved")
                  for commit in ("6430e4", "wrong00", "", None, 643049, "6430e49" + "0" * 34)]
        cases += [("28.0.4", "6430e49", timeout, "linux", "SIGTERM", "7.2.0",
                   "stop_profile_unproved") for timeout in (True, False, "10", 10.0, 9, 11, -1)]
        cases += [
            ("28.0.4", "6430e49", 10, "windows", "SIGTERM", "7.2.0", "stop_platform_unproved"),
            ("28.0.4", "6430e49", 10, "linux", "SIGINT", "7.2.0", "stop_signal_unproved"),
            ("28.0.4", "6430e49", 10, "linux", "SIGTERM", "7.1.0", "sdk_stop_semantics_unproved"),
        ]
        for version, commit, timeout, platform, signal, sdk, reason in cases:
            with self.subTest(version=version, commit=commit, timeout=timeout,
                              platform=platform, signal=signal, sdk=sdk):
                container = SimpleNamespace(id="controlled", reload=Mock(), attrs={
                    "Config": {"StopSignal": signal, "StopTimeout": timeout}})
                client = SimpleNamespace(
                    info=Mock(return_value={"ID": "engine", "OSType": platform}),
                    version=Mock(return_value={"Version": version, "GitCommit": commit}))
                with patch("docker.__version__", sdk), redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(witness.QualificationFailure, "^" + reason + "$"):
                        witness.resolve_profile(client, container)

    def test_contents_refuses_wrong_numeric_identity_before_version_io(self):
        for uid, gid in ((0, 65532), (65532, 0)):
            with self.subTest(uid=uid, gid=gid):
                with patch.object(witness.os, "getuid", return_value=uid), \
                        patch.object(witness.os, "getgid", return_value=gid), \
                        patch.object(witness.subprocess, "run", side_effect=AssertionError(
                            "version I/O reached before numeric identity admission")) as version:
                    with self.assertRaisesRegex(witness.QualificationFailure, "^numeric_uid$"):
                        witness.image_contents()
                    version.assert_not_called()

    def test_controller_capture_freezes_requested_mode_before_cleanup(self):
        context = {}
        witness.mark_controller(context, "artifact", "start", "contents")
        output = io.StringIO()
        with redirect_stdout(output):
            primary, reported = witness.capture_controller_failure("primary", context)
            witness.mark_controller(context, "cleanup", "remove")
            cleanup, cleanup_reported = witness.capture_controller_failure("cleanup", context)
        self.assertTrue(reported)
        self.assertTrue(cleanup_reported)
        self.assertEqual(primary, {"phase": "artifact", "operation": "start",
                                   "helper_mode": "contents"})
        self.assertEqual(cleanup, {"phase": "cleanup", "operation": "remove",
                                   "helper_mode": None})
        self.assertEqual([json.loads(line) for line in output.getvalue().splitlines()], [
            {"stage": "managed_cloudflared_controller_failure", "outcome": "unqualified",
             "role": "primary", **primary},
            {"stage": "managed_cloudflared_controller_failure", "outcome": "unqualified",
             "role": "cleanup", **cleanup},
        ])

    def test_controller_failure_output_refuses_candidate_context(self):
        valid = {"phase": "artifact", "operation": "reload", "helper_mode": "contents"}
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            for field in valid:
                self.assertFalse(witness.emit_controller_failure(
                    "primary", {**valid, field: "PRIVATE_CANDIDATE"}))
            self.assertFalse(witness.emit_controller_failure(
                "PRIVATE_CANDIDATE", valid))
            self.assertFalse(witness.emit_controller_failure(
                "primary", {**valid, "extra": "PRIVATE_CANDIDATE"}))
        self.assertEqual(output.getvalue(), "")

    def test_controller_primary_survives_cleanup_failure_and_cleanup_alone_refuses(self):
        primary = RuntimeError("PRIVATE_CANDIDATE")
        for cleanup_failed in (False, True):
            with self.subTest(cleanup_failed=cleanup_failed):
                with self.assertRaises(RuntimeError) as raised:
                    witness.finish_controller(primary, cleanup_failed)
                self.assertIs(raised.exception, primary)
        with self.assertRaisesRegex(witness.QualificationFailure, "^managed_cleanup_incomplete$"):
            witness.finish_controller(None, True)
        self.assertIsNone(witness.finish_controller(None, False))

    def test_controller_failed_emission_retains_capture_and_original_outcome(self):
        context = {"phase": "setup", "operation": "connect", "helper_mode": None}
        primary = RuntimeError("PRIVATE_CANDIDATE")
        with patch("builtins.print", side_effect=OSError("PRIVATE_CANDIDATE")):
            snapshot, reported = witness.capture_controller_failure("primary", context)
            self.assertFalse(reported)
            self.assertEqual(snapshot, context)
            self.assertIsNot(snapshot, context)
            self.assertFalse(witness.emit_qualification_failure(
                witness.QualificationFailure("package_inspection_state"), []))
            with self.assertRaises(RuntimeError) as raised:
                witness.finish_controller(primary, False)
            self.assertIs(raised.exception, primary)

    def test_only_allowlisted_qualification_reasons_survive(self):
        for failure, reason in (
            (witness.QualificationFailure("numeric_uid"), "numeric_uid"),
            (witness.QualificationFailure("PRIVATE_CANDIDATE"), "helper_exception"),
            (RuntimeError("numeric_uid"), "helper_exception"),
            (RuntimeError("PRIVATE_CANDIDATE"), "helper_exception"),
            (witness.QualificationFailure(["PRIVATE_CANDIDATE"]), "helper_exception"),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(witness.helper_failure_value(failure),
                                 {"outcome": "failure", "reason": reason})

    def test_nonzero_exit_preserves_failure_with_closed_diagnostics(self):
        cases = (
            ({"outcome": "failure", "reason": "numeric_uid"}, None, "valid_error"),
            (None, FileNotFoundError("PRIVATE_CANDIDATE"), "unavailable"),
            (None, ValueError("PRIVATE_CANDIDATE"), "invalid"),
            ({"outcome": "failure", "reason": "PRIVATE_CANDIDATE"}, None, "invalid"),
            ({"outcome": "failure", "reason": "numeric_uid",
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
                                                "^package_inspection_failed$"):
                        witness.completed_helper("contents", 7, Path("unused"),
                                                 time.monotonic() + 10)
                self.assertEqual(json.loads(output.getvalue()), {
                    "stage": "managed_cloudflared_helper", "mode": "contents",
                    "exit_code": 7, "result": availability,
                    **({"reason": "numeric_uid"} if availability == "valid_error" else {}),
                })
                self.assertNotIn("PRIVATE_CANDIDATE", output.getvalue())

    def test_exhausted_deadline_preserves_original_failure_without_read(self):
        output = io.StringIO()
        with patch.object(witness.os, "open") as opened, redirect_stdout(output):
            with self.assertRaisesRegex(witness.QualificationFailure,
                                        "^package_inspection_failed$"):
                witness.completed_helper("contents", 1, Path("unused"),
                                         time.monotonic() - 1)
        opened.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), {
            "stage": "managed_cloudflared_helper", "mode": "contents",
            "exit_code": 1, "result": "deadline_exhausted",
        })
        with patch.object(witness.os, "open") as opened:
            with self.assertRaisesRegex(witness.QualificationFailure, "^helper_deadline$"):
                witness.completed_helper("contents", 0, Path("unused"),
                                         time.monotonic() - 1)
        opened.assert_not_called()

    def test_zero_exit_rejects_failure_envelope_and_preserves_success_payload(self):
        for mode, payload in (
            ("contents", {"native_version": "2026.6.1"}),
        ):
            with self.subTest(mode=mode):
                with patch.object(witness, "read_helper_result", return_value=payload):
                    self.assertIs(witness.completed_helper(
                        mode, 0, Path("unused"), time.monotonic() + 10), payload)
                with patch.object(witness, "read_helper_result", return_value={
                    "outcome": "failure", "reason": "numeric_uid",
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
            self.assertEqual(emit.call_count, 1)
            for call in emit.call_args_list:
                self.assertEqual(call.args, (
                    {"outcome": "failure", "reason": "helper_exception"},))
        output = io.StringIO()
        with patch.object(witness, "emit_helper", side_effect=OSError("PRIVATE_CANDIDATE")), \
                redirect_stdout(output), redirect_stderr(output):
            self.assertFalse(witness.retain_helper_failure("contents", failure))
        self.assertEqual(output.getvalue(), "")
