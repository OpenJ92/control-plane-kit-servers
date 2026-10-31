"""Exercise the actual pure producer selector; no Docker or registry calls."""
from pathlib import Path
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "select_repository_digest.sh"
REPOSITORY = "ghcr.io/openj92/control-plane-kit-servers/hello-server"


class RepositoryDigestSelectionTests(unittest.TestCase):
    def select(self, content):
        return subprocess.run(["sh", str(SCRIPT), REPOSITORY], input=content,
            capture_output=True, text=True, timeout=5, check=False)

    def test_exact_repository_is_selected_regardless_of_array_order(self):
        expected = REPOSITORY + "@sha256:" + "a" * 64
        foreign = "ghcr.io/elsewhere/counter-witness@sha256:" + "b" * 64
        for values in ((foreign, expected), (expected, foreign)):
            with self.subTest(values=values):
                result = self.select("\n".join(values) + "\n")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected + "\n")

    def test_absent_ambiguous_wrong_repository_and_malformed_digests_refuse(self):
        valid = REPOSITORY + "@sha256:" + "a" * 64
        for content in ("", "\n", "ghcr.io/elsewhere/counter-witness@sha256:" + "a" * 64,
                REPOSITORY + "-other@sha256:" + "a" * 64,
                valid + "\n" + valid,
                valid + "\n" + REPOSITORY + "@sha256:" + "b" * 64,
                REPOSITORY + "@sha256:" + "A" * 64,
                REPOSITORY + "@sha256:" + "a" * 63,
                REPOSITORY + "@sha256:" + "a" * 65,
                REPOSITORY + "@sha512:" + "a" * 64):
            with self.subTest(content=content):
                result = self.select(content)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
