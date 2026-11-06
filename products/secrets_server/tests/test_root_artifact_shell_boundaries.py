"""Actual workflow/smoke shell refusal boundaries; no real Docker or registry."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
SOURCE = "1" * 40
CPK = "ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:" + "a" * 64
SECRETS = "ghcr.io/openj92/control-plane-kit-servers/secrets-server@sha256:" + "b" * 64
DOCKER = r'''
import json, os, pathlib, sys
with pathlib.Path(os.environ["BOUNDARY_CALLS"]).open("a") as target:
    target.write(json.dumps(sys.argv[1:]) + "\n")
sys.exit(73)
'''


class RootArtifactShellBoundaryTests(unittest.TestCase):
    def run_shell(self, script, environment, *, shell="sh"):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            docker = root / "docker"
            docker.write_text("#!" + sys.executable + "\n" + DOCKER)
            docker.chmod(0o700)
            calls = root / "calls"
            env = {**os.environ, **environment, "BOUNDARY_CALLS": str(calls),
                   "PATH": str(root) + os.pathsep + os.environ["PATH"]}
            result = subprocess.run([shell, "-c", script], cwd=ROOT, env=env,
                text=True, capture_output=True, timeout=15, check=False)
            observed = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
        return result, observed

    def tuple(self):
        return {"CPK_ROOT_ARTIFACT_MODE": "published-digest", "CPK_ROOT_CPK_IMAGE": CPK,
                "CPK_ROOT_SECRETS_IMAGE": SECRETS, "CPK_ROOT_SOURCE_REVISION": SOURCE,
                "CPK_WRAPPER_ARTIFACT_MODE": "source-built"}

    def test_real_preload_rejects_invalid_root_tuple_before_any_docker_acquisition(self):
        self.assertIsNotNone(shutil.which("jq"), "owning test image must provide real jq")
        workflow = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())
        steps = workflow["jobs"]["docker-tests"]["steps"]
        scripts = [step["run"] for step in steps if "optional artifact tuple" in step.get("name", "")]
        self.assertEqual(len(scripts), 1)
        base = self.tuple()
        cases = [{**base, "CPK_ROOT_ARTIFACT_MODE": "unknown"},
                 {**base, "CPK_ROOT_ARTIFACT_MODE": "source-built"},
                 {**base, "CPK_ROOT_SECRETS_IMAGE": ""},
                 {**base, "CPK_ROOT_CPK_IMAGE": SECRETS},
                 {**base, "CPK_ROOT_SOURCE_REVISION": "develop"},
                 {**base, "CPK_ROOT_CPK_IMAGE": CPK + "\n"}]
        for candidate in cases:
            with self.subTest(candidate=candidate):
                result, calls = self.run_shell(scripts[0], candidate, shell="bash")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [], "invalid tuple reached Docker instead of failing input admission")
                self.assertIn("current root artifact", result.stderr.lower())

    def test_selected_profile_never_builds_and_missing_cache_never_pulls(self):
        for role, reference, prefix in (("cpk", CPK, "CPK_SERVER"),
                                        ("secrets", SECRETS, "CPK_SECRETS")):
            script = "sh scripts/" + ("cpk_server" if role == "cpk" else "secrets_server") + "_image_smoke.sh"
            base = {**self.tuple(), prefix + "_IMAGE": reference,
                    prefix + "_SMOKE_PROFILE": "wrapped-artifact", prefix + "_BUILD_IMAGE": "0",
                    "CPK_SERVERS_TEST_IMAGE": "fixture-controller", "CPK_SECRETS_BUILD_CONTROLLER": "0"}
            with self.subTest(role=role, case="build-forbidden"):
                result, calls = self.run_shell(script, {**base, prefix + "_BUILD_IMAGE": "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [])
            with self.subTest(role=role, case="cache-missing"):
                result, calls = self.run_shell(script, base)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(any(args[:2] == ["image", "inspect"] and reference in args for args in calls),
                                "selected wrapped artifact never reached real cache admission")
                self.assertFalse(any(args[:1] in (["pull"], ["build"], ["push"], ["create"], ["run"])
                                     for args in calls))
