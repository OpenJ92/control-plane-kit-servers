"""Public dependency preflight: real report function, finite metadata facts."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("grandparent_image_check",
    ROOT / "products/cpk_server/tests/grandparent_image_check.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
LOCK = ROOT / "products/cpk_server/mcp-grandparent-public-lock.json"


class PublicInventoryTests(unittest.TestCase):
    def versions(self, *, mismatch=False):
        values = {p["name"]: p["version"] for p in json.loads(LOCK.read_text())["packages"]}
        # Missing packages are additions, never inferred installed versions.
        values.pop("mcp")
        values["fastapi"] = "0.141.1"
        if mismatch:
            values["pydantic"] = "2.12.0"
        def version(name):
            if name not in values:
                raise CHECK.metadata.PackageNotFoundError(name)
            return values[name]
        return version

    def report(self, *, mismatch=False, require_match=False):
        output = io.StringIO()
        with patch.object(CHECK.metadata, "version", side_effect=self.versions(mismatch=mismatch)), \
                patch.object(CHECK.metadata, "distribution", side_effect=CHECK.metadata.PackageNotFoundError), \
                patch.object(CHECK.platform, "machine", return_value="x86_64"), \
                contextlib.redirect_stdout(output):
            CHECK.base_public_inventory(LOCK, require_match=require_match)
        return json.loads(output.getvalue())

    def test_missing_and_same_version_have_explicit_bounded_delta(self):
        observed = self.report(require_match=True)
        self.assertEqual(observed["status"], "ready-no-version-changes")
        self.assertEqual(observed["packages"]["mcp"]["delta"], "add")
        self.assertEqual(observed["packages"]["pydantic"]["delta"], "reseal-same-version")
        self.assertFalse(observed["server_started"])
        self.assertFalse(observed["credential_or_configuration_read"])

    def test_version_difference_reports_review_and_refuses_build_admission(self):
        observed = self.report(mismatch=True)
        self.assertEqual(observed["status"], "review-required")
        self.assertEqual(observed["mismatches"], ["pydantic"])
        with self.assertRaises(ValueError):
            self.report(mismatch=True, require_match=True)
