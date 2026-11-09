"""Fake CLI proofs for the focused receiver's destructive cleanup boundary.

Executed only by the owning Docker gate; these never contact a real daemon.
"""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
from tempfile import TemporaryDirectory
import textwrap
import unittest
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[3]
FAKE_DOCKER = r'''
import json, os, pathlib, sys
a = sys.argv[1:]
mode = os.environ["FAKE_CASE"]
run = os.environ["FAKE_RUN"]
with open(os.environ["FAKE_CALLS"], "a") as log:
    log.write(json.dumps(a) + "\n")
if a[0] == "info":
    print("fixture-daemon")
elif a[:2] == ["context", "show"]:
    print("fixture-local")
elif a[:2] == ["context", "inspect"]:
    print("unix:///var/run/docker.sock")
elif a[:2] == ["image", "ls"]:
    if mode == "preflight-read-failure": sys.exit(17)
elif a[:2] == ["network", "ls"]:
    if mode == "post-remove-read-failure" and any(x.startswith("id=") for x in a): sys.exit(18)
elif a[:2] == ["container", "ls"]:
    if mode == "run-collision" and any(x.startswith("label=") for x in a): print("c" * 64)
elif a[:2] == ["image", "inspect"]:
    if "--format" in a:
        if a[a.index("--format")+1] == "{{.Id}}": print("sha256:"+"a"*64)
        else:
            print(json.dumps({"id":"sha256:"+"a"*64,
                "repo_digests":["localhost/control-plane-kit-servers/cpk-server@sha256:"+"a"*64],
                "os":"linux", "architecture":"amd64", "cmd":["python","-m","control_plane_kit_servers_cpk_server.server"]}))
elif a[:2] == ["buildx", "build"]:
    pathlib.Path(a[a.index("--iidfile")+1]).write_text("sha256:"+"a"*64+"\n")
    pathlib.Path(a[a.index("--metadata-file")+1]).write_text(json.dumps({
        "containerimage.digest":"sha256:"+"a"*64, "containerimage.config.digest":"sha256:"+"b"*64,
        "containerimage.descriptor":{"digest":"sha256:"+"a"*64,"mediaType":"application/vnd.oci.image.index.v1+json"}}))
elif a[0] == "run":
    print("{}")
elif a[0] == "inspect":
    print("10001")
elif a[:2] == ["network", "create"]:
    print("d" * 64)
elif a[:2] == ["volume", "ls"]:
    if mode == "post-remove-read-failure": sys.exit(19)
elif a[:2] == ["network", "inspect"]:
    print(run)
elif a[:2] == ["network", "rm"]:
    pass
else:
    sys.exit(23)
'''
FAKE_GIT = r'''
import os, pathlib, sys
a = sys.argv[1:]
if a[:1] == ["status"]:
    counter = pathlib.Path(os.environ["FAKE_STATUS_CALLS"])
    count = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(count+1))
    if os.environ["FAKE_CASE"] == "source-became-dirty" and count > 0:
        print(" M changed-source")
elif a[:1] == ["rev-parse"]:
    print("e" * 40)
elif a[:1] == ["diff"]:
    pass
elif a[:1] == ["archive"]:
    print("fake archive consumed only by fake Docker")
else:
    sys.exit(23)
'''


class CpkReceiverShellTests(unittest.TestCase):
    def run_fixture(self, mode, *, existing_receipt=False, diagnostic=False, image_override=None):
        with TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            run = "cpk163-shell-" + uuid4().hex
            records = Path("/tmp").resolve() / run
            if existing_receipt:
                records.mkdir()
                (records / "result.json").write_text("foreign-receipt")
            binaries = parent / "bin"
            binaries.mkdir()
            for name, source in (("docker", FAKE_DOCKER), ("git", FAKE_GIT)):
                path = binaries / name
                path.write_text("#!" + sys.executable + "\n" + textwrap.dedent(source).lstrip())
                path.chmod(0o700)
            calls = parent / "calls.jsonl"
            environment = {**os.environ,
                "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
                "FAKE_CASE": mode, "FAKE_RUN": run, "FAKE_CALLS": str(calls),
                "FAKE_STATUS_CALLS": str(parent / "status-count"),
                "CPK_SERVER_SMOKE_PROFILE":"wrapped-receiver", "CPK_SERVER_BUILD_IMAGE":"1",
                "CPK_SERVER_IMAGE":"localhost/control-plane-kit-servers/cpk-server:cpk163-fixture",
                "CPK_SERVERS_TEST_IMAGE":"sha256:" + "f" * 64,
                "CPK_RECEIVER_RUN": run, "CPK_RECEIVER_RECORDS": str(records),
                "CPK_RECEIVER_POSTGRES_IMAGE":"docker.io/library/postgres@sha256:" + "b" * 64,
                "CPK_RECEIVER_DAEMON_ID":"fixture-daemon", "CPK_RUNTIME_INTERPRETERS":"none",
                "CPK_SERVER_SMOKE_HOST":"127.0.0.1"}
            if diagnostic:
                environment.update(CPK_SERVER_SMOKE_PROFILE="wrapped-receiver-diagnostic",
                    CPK_SERVER_BUILD_IMAGE="0",
                    CPK_SERVER_IMAGE="localhost/control-plane-kit-servers/cpk-server@sha256:4846a9005108e925149b2869214c3f32dbdbd4d4953159af532297081e80fe28")
            if image_override is not None:
                environment["CPK_SERVER_IMAGE"] = image_override
            for key in ("DOCKER_HOST", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
                environment.pop(key, None)
            try:
                result = subprocess.run(["sh", "scripts/cpk_server_image_smoke.sh"], cwd=ROOT,
                    env=environment, capture_output=True, text=True, timeout=15, check=False)
                observed = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
                receipt = (records / "result.json").read_text() if (records / "result.json").exists() else None
                return result.returncode, observed, receipt, records.exists()
            finally:
                if records.exists():
                    shutil.rmtree(records)

    def test_run_collision_cannot_remove_preexisting_fixture_or_write_receipt(self):
        status, calls, receipt, exists = self.run_fixture("run-collision")
        self.assertNotEqual(status, 0)
        self.assertFalse(exists)
        self.assertIsNone(receipt)
        self.assertFalse(any("rm" in call or call[:2] == ["buildx", "build"] for call in calls))

    def test_failed_preflight_absence_read_is_unknown_and_cannot_build(self):
        status, calls, receipt, exists = self.run_fixture("preflight-read-failure")
        self.assertNotEqual(status, 0)
        self.assertFalse(exists)
        self.assertIsNone(receipt)
        self.assertFalse(any("rm" in call or call[:2] == ["buildx", "build"] for call in calls))

    def test_existing_receipt_directory_is_untouched(self):
        status, calls, receipt, _ = self.run_fixture("run-collision", existing_receipt=True)
        self.assertNotEqual(status, 0)
        self.assertEqual(receipt, "foreign-receipt")
        self.assertEqual(calls, [])

    def test_failed_post_remove_read_never_becomes_verified_cleanup(self):
        status, calls, receipt, _ = self.run_fixture("post-remove-read-failure")
        self.assertNotEqual(status, 0)
        self.assertTrue(any(call[:2] == ["network", "rm"] for call in calls))
        self.assertEqual(json.loads(receipt)["cleanup"], "unverified")
        self.assertFalse(json.loads(receipt)["signed_pair_verified"])

    def test_changed_source_after_build_stops_before_fixture_start(self):
        status, calls, receipt, _ = self.run_fixture("source-became-dirty")
        self.assertNotEqual(status, 0)
        self.assertEqual(sum(call[:2] == ["buildx", "build"] for call in calls), 1)
        self.assertFalse(any(call[:2] == ["network", "create"] or call[:1] == ["run"] for call in calls))
        self.assertEqual(json.loads(receipt)["exit_code"], status)

    def test_retained_diagnostic_rejects_another_image_before_daemon_access(self):
        status, calls, receipt, exists = self.run_fixture("run-collision", diagnostic=True,
            image_override="localhost/control-plane-kit-servers/cpk-server@sha256:" + "a" * 64)
        self.assertNotEqual(status, 0)
        self.assertEqual(calls, [])
        self.assertIsNone(receipt)
        self.assertFalse(exists)

    def test_retained_diagnostic_collision_cannot_build_or_delete(self):
        status, calls, receipt, exists = self.run_fixture("run-collision", diagnostic=True)
        self.assertNotEqual(status, 0)
        self.assertFalse(exists)
        self.assertIsNone(receipt)
        self.assertFalse(any("rm" in call or call[:2] == ["buildx", "build"] for call in calls))
