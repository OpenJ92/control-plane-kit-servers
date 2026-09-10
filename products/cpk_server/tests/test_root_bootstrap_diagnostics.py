"""Closed bootstrap failure projection without Docker, receipts or raw errors."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from control_plane_kit_servers_cpk_server import bootstrap as api
from control_plane_kit_servers_cpk_server import bootstrap_cli as cli
from control_plane_kit_servers_cpk_server import bootstrap_runtime
from products.cpk_server.tests import live_root_bootstrap as witness


class RootBootstrapDiagnosticTests(unittest.TestCase):
    def test_numeric_groups_include_sealed_image_membership_and_declared_socket(self):
        baseline = witness.CPK_IMAGE_ACCOUNT
        expected = baseline.expected_groups(baseline.image_reference, 43210)
        self.assertEqual(expected, frozenset({10001, 100, 43210}))
        matches, _ = witness.numeric_group_check(10001, (100, 43210, 10001), expected, 43210)
        self.assertTrue(matches)

    def test_numeric_groups_reject_missing_baseline_or_declared_and_unexpected_membership(self):
        baseline = witness.CPK_IMAGE_ACCOUNT
        expected = baseline.expected_groups(baseline.image_reference, 43210)
        for groups in ((43210,), (100,), (100, 43210, 54321)):
            with self.subTest(groups=groups):
                matches, _ = witness.numeric_group_check(10001, groups, expected, 43210)
                self.assertFalse(matches)

    def test_numeric_group_baseline_requires_exact_reviewed_image(self):
        baseline = witness.CPK_IMAGE_ACCOUNT
        with self.assertRaisesRegex(AssertionError, "baseline does not match"):
            baseline.expected_groups("ghcr.io/example/cpk@sha256:" + "0" * 64, 43210)

    def project_through_cli(self, error):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["bootstrap", "inspect", "--state", "/unused"]), \
                patch.object(cli, "inspect_root_bootstrap", side_effect=error), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(cli.main(), 1)
        self.assertEqual(output.getvalue(), "")
        return json.loads(errors.getvalue())

    def test_known_failure_keeps_inner_stage_and_leaves_history_unchanged(self):
        continued = []
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "receipt.json"
            receipt.write_bytes(b"existing history")
            with self.assertRaises(api.RootBootstrapDiagnostic) as caught:
                with api.bootstrap_stage(api.BootstrapStage.LAUNCHER):
                    with api.bootstrap_stage(api.BootstrapStage.INSPECT_DRIVER_IMAGE):
                        raise api.RootBootstrapError("bootstrap driver image is unavailable")
                    continued.append(True)
            self.assertEqual(continued, [])
            self.assertEqual(receipt.read_bytes(), b"existing history")
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["receipt.json"])
        diagnostic = caught.exception
        with self.assertRaises(api.RootBootstrapDiagnostic) as again:
            with api.bootstrap_stage(api.BootstrapStage.LOCK_STATE):
                raise diagnostic
        self.assertIs(again.exception, diagnostic)
        self.assertEqual(self.project_through_cli(diagnostic), {
            "status": "hold", "message": "bootstrap result could not be verified; inspect the private receipt",
            "stage": "inspect-driver-image", "reason": "driver-image-unavailable"})

    def test_untrusted_errors_and_attributes_never_reach_public_output(self):
        sentinel = "credential=private-value /private/material provider-body"
        tampered = api.RootBootstrapDiagnostic(api.BootstrapStage.DECODE_GRAPH, api.BootstrapReason.UNEXPECTED_ERROR)
        tampered.stage = sentinel
        for error in (RuntimeError(sentinel), api.RootBootstrapError(sentinel), tampered):
            error.reason = sentinel
            error.__cause__ = ValueError(sentinel)
            result = self.project_through_cli(error)
            self.assertEqual(set(result), {"status", "message", "stage", "reason"})
            self.assertEqual(result["status"], "hold")
            self.assertEqual(result["stage"], "launcher")
            self.assertEqual(result["reason"], "unexpected-error")
            self.assertNotIn(sentinel, json.dumps(result))
        with self.assertRaises(TypeError):
            api.RootBootstrapDiagnostic(sentinel, api.BootstrapReason.UNEXPECTED_ERROR)

    def test_persistence_failure_is_classified_without_fabricating_a_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(bootstrap_runtime.os, "open", side_effect=OSError("secret provider body")):
                with self.assertRaises(api.RootBootstrapDiagnostic) as caught:
                    bootstrap_runtime._save(Path(directory), {})
            self.assertEqual(list(Path(directory).iterdir()), [])
        result = self.project_through_cli(caught.exception)
        self.assertEqual(set(result), {"status", "message", "stage", "reason"})
        self.assertEqual(result["stage"], "persist-receipt")
        self.assertEqual(result["reason"], "unexpected-error")

    def test_base_exception_identity_crosses_guard_and_cli_unchanged(self):
        for error in (KeyboardInterrupt(), SystemExit(7)):
            with self.assertRaises(type(error)) as caught:
                with api.bootstrap_stage(api.BootstrapStage.DECODE_GRAPH):
                    raise error
            self.assertIs(caught.exception, error)
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(sys, "argv", ["bootstrap", "inspect", "--state", "/unused"]), \
                    patch.object(cli, "inspect_root_bootstrap", side_effect=error), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                with self.assertRaises(type(error)) as caught:
                    cli.main()
            self.assertIs(caught.exception, error)
            self.assertEqual((output.getvalue(), errors.getvalue()), ("", ""))
