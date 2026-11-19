"""The existing producer binds its two root roles before any publication."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = "1" * 40
GIT = r'''
import os, sys
if sys.argv[1:] == ["rev-parse", "HEAD"]:
    print("1" * 40)
elif sys.argv[1:] == ["status", "--porcelain"]:
    if os.environ["PRODUCER_CASE"] == "dirty": print(" M tracked-file")
else:
    sys.exit(95)
'''
DOCKER = r'''
import json, os, pathlib, sys
args = sys.argv[1:]
path = pathlib.Path(os.environ["PRODUCER_CALLS"])
prior = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
with path.open("a") as target: target.write(json.dumps(args) + "\n")
case = os.environ["PRODUCER_CASE"]
role = os.environ["PRODUCER_ROLE"]
image_id = "sha256:" + ("d" if case == "identity-drift" and any(a[:1] == ["push"] for a in prior) else "c") * 64
revision = ("2" if case == "wrong-source" else "1") * 40
user = "0" if case == "wrong-user" else ("10001" if role == "cpk-server" else "10006")
arch = "arm64" if case == "wrong-platform" else "amd64"
reference = "ghcr.io/openj92/control-plane-kit-servers/" + role + "@sha256:" + "a" * 64
if args[:2] == ["image", "inspect"]:
    if "--format" in args:
        template = args[args.index("--format") + 1]
        if "RepoDigests" in template: print(reference)
        elif "Architecture" in template: print("linux/" + arch)
        elif "Config.User" in template: print(user)
        elif "org.opencontainers.image.revision" in template: print(revision)
        elif ".Id" in template: print(image_id)
        else: sys.exit(94)
    else:
        print(json.dumps([{"Id": image_id, "Os": "linux", "Architecture": arch,
            "RepoDigests": [reference], "Config": {"User": user,
            "Labels": {"org.opencontainers.image.revision": revision}}}]))
elif args[:1] not in (["run"], ["build"], ["push"]):
    sys.exit(93)
'''


class RootArtifactProducerTests(unittest.TestCase):
    def produce(self, role, case="valid"):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, source in (("docker", DOCKER), ("git", GIT)):
                path = root / name
                path.write_text("#!" + sys.executable + "\n" + source)
                path.chmod(0o700)
            calls = root / "calls"
            env = {**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                "PRODUCER_CALLS": str(calls), "PRODUCER_CASE": case, "PRODUCER_ROLE": role,
                "GHCR_OWNER": "openj92", "GHCR_PACKAGE": "control-plane-kit-servers"}
            result = subprocess.run(["sh", "scripts/publish_product_image.sh", role, "root-191-" + SOURCE],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=15, check=False)
            observed = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
        return result, observed

    def test_each_root_producer_builds_exact_platform_revision_and_reports_actual_identity(self):
        for role in ("cpk-server", "secrets-server"):
            with self.subTest(role=role):
                result, calls = self.produce(role)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                builds = [args for args in calls if args[:1] == ["build"]]
                self.assertEqual(len(builds), 1)
                self.assertIn("--platform", builds[0])
                self.assertEqual(builds[0][builds[0].index("--platform") + 1], "linux/amd64")
                self.assertIn("org.opencontainers.image.revision=" + SOURCE, builds[0])
                self.assertEqual(sum(args[:1] == ["push"] for args in calls), 1)
                self.assertIn("sha256:" + "c" * 64, result.stdout)
                self.assertIn("ghcr.io/openj92/control-plane-kit-servers/" + role + "@sha256:" + "a" * 64,
                              result.stdout)
                self.assertIn(SOURCE, result.stdout)

    def test_dirty_source_refuses_before_build_or_publication(self):
        for role in ("cpk-server", "secrets-server"):
            with self.subTest(role=role):
                result, calls = self.produce(role, "dirty")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(args[:1] in (["build"], ["push"]) for args in calls))

    def test_wrong_platform_user_or_revision_refuses_before_push(self):
        for role in ("cpk-server", "secrets-server"):
            for case in ("wrong-platform", "wrong-user", "wrong-source"):
                with self.subTest(role=role, case=case):
                    result, calls = self.produce(role, case)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(any(args[:1] == ["push"] for args in calls))

    def test_post_push_identity_drift_is_failure_without_retry_or_image_deletion(self):
        for role in ("cpk-server", "secrets-server"):
            with self.subTest(role=role):
                result, calls = self.produce(role, "identity-drift")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sum(args[:1] == ["push"] for args in calls), 1)
                self.assertFalse(any(args[:1] == ["rmi"] or args[:2] == ["image", "rm"] for args in calls))
