"""Exercise the actual smoke finish boundary, without a second cleanup model."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/secrets_server_image_smoke.sh"
STUB = r'''
import json, os, pathlib, sys
args = sys.argv[1:]
path = pathlib.Path(os.environ["CLEANUP_COMMANDS"])
prior = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
with path.open("a") as output:
    output.write(json.dumps(args) + "\n")
scenario = os.environ["CLEANUP_SCENARIO"]
if args[:1] == ["ps"]:
    number = sum(item[:1] == ["ps"] for item in prior)
    if scenario == "inventory-failed" and number == 0:
        sys.exit(31)
    if scenario == "residue" or (scenario in ("removed", "removal-failed") and number == 0):
        print("owned-container")
elif args[:1] == ["rm"]:
    if args[-1] != "owned-container":
        sys.exit(90)
    if scenario == "removal-failed":
        sys.exit(32)
elif args[:2] not in (["volume", "ls"], ["network", "ls"]):
    sys.exit(91)
'''


class ImageCleanupReportingTests(unittest.TestCase):
    def run_finish(self, scenario, body_status=0, private_residue=False):
        source = SCRIPT.read_text()
        boundary = 'if [ "$BUILD_IMAGE" = "1" ]; then'
        self.assertEqual(source.count(boundary), 1)
        # Only source the actual declarations/functions/trap before image/runtime effects.
        prefix = source.split(boundary, 1)[0]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            stub = root / "docker"
            stub.write_text("#!" + sys.executable + "\n" + STUB)
            stub.chmod(0o700)
            commands = root / "commands.jsonl"
            env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                "CPK_SECRETS_SMOKE_PROFILE": "published-baseline", "CPK_SECRETS_BUILD_IMAGE": "0",
                "CPK_SECRETS_BUILD_CONTROLLER": "0", "CPK_SECRETS_IMAGE":
                    "ghcr.io/openj92/control-plane-kit-servers/secrets-server@sha256:" + "b" * 64,
                "CLEANUP_SCENARIO": scenario, "CLEANUP_COMMANDS": str(commands)}
            shell = prefix + "\nCONTROL_RECORDS=" + shlex.quote(str(root / "private-records")) + "\n"
            (root / "private-records").mkdir(mode=0o700)
            if private_residue:
                (root / "private-records" / "unrecognized").write_text("retained marker")
            shell += "exit " + str(body_status) + "\n"
            result = subprocess.run(["sh", "-c", shell], env=env, cwd=ROOT,
                text=True, capture_output=True, timeout=15, check=False)
            observed = [json.loads(line) for line in commands.read_text().splitlines()] if commands.exists() else []
            private_absent = not (root / "private-records").exists()
        return result, observed, private_absent

    def assert_scope(self, observed):
        for args in observed:
            if args[:1] == ["ps"] or args[:2] in (["volume", "ls"], ["network", "ls"]):
                self.assertIn("--filter", args)
                self.assertTrue(args[args.index("--filter") + 1].startswith(
                    "label=cpk.test-run=cpk-secrets-image-smoke-"))
            if args[:1] == ["rm"]:
                self.assertEqual(args[-1], "owned-container")
        self.assertFalse(any(args[:1] in (["pull"], ["push"], ["build"], ["rmi"])
                             or args[:2] == ["image", "rm"] for args in observed))

    def test_success_requires_absence_and_private_cleanup_before_one_final_pass(self):
        for scenario in ("absent", "removed"):
            with self.subTest(scenario=scenario):
                result, observed, private_absent = self.run_finish(scenario)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(private_absent)
                self.assertEqual(result.stdout.count("secrets-server image smoke passed"), 1)
                self.assertGreaterEqual(sum(args[:1] == ["ps"] for args in observed), 2)
                self.assert_scope(observed)

    def test_failed_inventory_or_removal_cannot_become_empty_success(self):
        for scenario in ("inventory-failed", "removal-failed"):
            with self.subTest(scenario=scenario):
                result, observed, _ = self.run_finish(scenario)
                self.assertNotEqual(result.returncode, 0, "failed Docker operation was masked")
                self.assertNotIn("secrets-server image smoke passed", result.stdout)
                self.assertLessEqual(sum(args[:1] == ["rm"] for args in observed), 1)
                self.assert_scope(observed)

    def test_observed_residue_is_failure_without_repeated_removal_or_pass(self):
        result, observed, _ = self.run_finish("residue")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("secrets-server image smoke passed", result.stdout)
        self.assertEqual(sum(args[:1] == ["rm"] for args in observed), 1)
        self.assert_scope(observed)

    def test_prior_failure_survives_successful_cleanup_without_pass(self):
        result, observed, private_absent = self.run_finish("absent", body_status=17)
        self.assertEqual(result.returncode, 17)
        self.assertTrue(private_absent)
        self.assertNotIn("secrets-server image smoke passed", result.stdout)
        self.assert_scope(observed)

    def test_private_file_residue_refuses_final_pass_and_is_retained(self):
        result, observed, private_absent = self.run_finish("absent", private_residue=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(private_absent)
        self.assertNotIn("secrets-server image smoke passed", result.stdout)
        self.assert_scope(observed)
