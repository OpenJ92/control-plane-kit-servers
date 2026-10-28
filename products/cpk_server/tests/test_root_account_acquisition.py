"""Diagnostic command admission only; never acquires images, tools or a mount."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/acquire_root_accounts.sh"
REFERENCE = "ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:" + "b" * 64
SOURCE = "a" * 40


class RootAccountAcquisitionTests(unittest.TestCase):
    def call(self, reference, source, output, **environment):
        env = {**os.environ, "GITHUB_ACTIONS": "false", "GH_TOKEN": "private-token-canary", **environment}
        result = subprocess.run(["bash", str(SCRIPT), reference, source, str(output)],
            env=env, capture_output=True, text=True, timeout=5, check=False)
        self.assertNotIn("private-token-canary", result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        return result

    def test_invalid_reference_or_source_refuses_before_acquisition_and_evidence_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            for reference, source in ((REFERENCE.replace("cpk-server", "secrets-server"), SOURCE),
                    (REFERENCE.replace("@sha256:" + "b" * 64, ":latest"), SOURCE),
                    (REFERENCE, "a" * 7), (REFERENCE, SOURCE + "\n"), (REFERENCE + "\n", SOURCE)):
                with self.subTest(reference=reference, source=source):
                    self.call(reference, source, Path(directory) / "new-output", GITHUB_ACTIONS="true")

    def test_valid_tuple_requires_the_producer_job_context_without_echoing_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.call(REFERENCE, SOURCE, Path(directory) / "new-output")
            self.assertIn("account inspection HOLD", result.stderr)
