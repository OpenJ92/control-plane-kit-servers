"""Diagnostic command admission only; never acquires images, tools or a mount."""
import os
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/acquire_root_accounts.sh"
REFERENCE = "ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:" + "b" * 64
SOURCE = "a" * 40


class RootAccountAcquisitionTests(unittest.TestCase):
    def commands(self, root, failure):
        """External process doubles only; no daemon, filesystem mount or provider."""
        commands = root / "commands"
        commands.mkdir()
        program = '''import json, os, pathlib, sys
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ["EVENTS"], "a") as stream:
    stream.write(json.dumps([name, args]) + "\\n")
failure = os.environ["FAILURE"]
if name == "id":
    print("1001")
elif name == "docker":
    if args[0] == "ps":
        if failure == "remaining" and pathlib.Path(os.environ["EVENTS"] + ".ran").exists():
            print("synthetic-owned-container")
        sys.exit(23 if failure == "docker" else 0)
    if args[0] == "image":
        print("linux/amd64" if args[-1] == "{{.Os}}/{{.Architecture}}" else "sha256:" + "c" * 64)
    elif args[0] == "run":
        if "TEST_RUN_STATUS" in os.environ:
            pathlib.Path(os.environ["EVENTS"] + ".ran").touch()
            sys.stderr.write(os.environ.get("TEST_RUN_ERROR", ""))
            sys.stdout.write(os.environ.get("TEST_RUN_OUTPUT", ""))
            sys.exit(int(os.environ["TEST_RUN_STATUS"]))
        sys.exit(17)  # Never simulate successful unpack or account evidence.
elif name == "findmnt":
    marker = pathlib.Path(os.environ["EVENTS"] + ".mount")
    after = marker.exists()
    marker.touch()
    if after and failure == "mount":
        sys.exit(1)  # An empty failed observation is not absence.
    rows = [{"target": "/", "source": "/dev/root"}]
    if not after:
        rows.append({"target": os.environ["MOUNT"], "source": os.environ["LOOP"]})
    print(json.dumps({"filesystems": rows}))
elif name == "sudo":
    if "--associated" in args:
        sys.exit(31 if failure == "loop" else 0)
    if "BACK-FILE" in args:
        print(os.environ["BACKING"])
elif name == "skopeo":
    if args[0] == "login":
        sys.stdin.read()
        pathlib.Path(args[args.index("--authfile") + 1]).write_text("{}")
    elif args[0] == "inspect":
        print("{}")  # The metadata controller must not execute in this double.
    else:
        sys.exit(99)
else:
    sys.exit(99)
'''
        for name in ("docker", "sudo", "findmnt", "id", "skopeo"):
            path = commands / name
            path.write_text("#!" + sys.executable + "\n" + program)
            path.chmod(0o700)
        return {**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"],
            "EVENTS": str(root / "events"), "FAILURE": failure,
            "MOUNT": str(root / "mount"), "BACKING": str(root / "backing"), "LOOP": "/dev/synthetic-loop"}

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

    def test_failed_empty_inventories_hold_before_candidate_promotion(self):
        for failure in ("docker", "mount", "loop"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                env = self.commands(root, failure)
                (root / "mount").mkdir()
                (root / "backing").write_bytes(b"owned fixture")
                result = subprocess.run(["bash", "-c",
                    'source "$1"; RUN=synthetic; cleanup_acquisition; printf candidate',
                    "test", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=5, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("candidate", result.stdout)
                self.assertTrue((root / "backing").exists())
                events = [json.loads(line) for line in (root / "events").read_text().splitlines()]
                if failure == "mount":
                    self.assertFalse(any(name == "sudo" and "--detach" in args for name, args in events))

    def test_both_controller_paths_mount_only_the_reviewed_source_file(self):
        for mode in ("metadata", "offline"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                env = self.commands(root, "run")
                env.update(GH_TOKEN="private-token-canary", GITHUB_ACTOR="synthetic")
                if mode == "metadata":
                    work = root / "work"
                    work.mkdir()
                    command = ["bash", str(SCRIPT), "--acquire", REFERENCE, SOURCE,
                        str(work), "sha256:" + "c" * 64, "synthetic"]
                else:
                    (root / "input").mkdir()
                    (root / "tools").mkdir()
                    command = ["sh", str(SCRIPT.with_name("inspect_root_accounts.sh")),
                        "sha256:" + "c" * 64, str(root / "input"), str(root / "tools"),
                        str(root / "output"), REFERENCE, SOURCE]
                result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("private-token-canary", result.stdout + result.stderr)
                events = [json.loads(line) for line in (root / "events").read_text().splitlines()]
                runs = [args for name, args in events if name == "docker" and args[0] == "run"]
                self.assertEqual(len(runs), 1)
                mounts = [runs[0][index + 1] for index, arg in enumerate(runs[0]) if arg == "--mount"]
                source_mount = [value for value in mounts if "target=/source/" in value]
                self.assertEqual(source_mount, ["type=bind,source=" + str(SCRIPT.with_name("root_account_projection.py"))
                    + ",target=/source/root_account_projection.py,readonly"])
                self.assertFalse(any("auth.json" in value or "target=/source," in value for value in mounts))

    def offline(self, root, *, code, error="", output="", failure="run", parent=False):
        env = self.commands(root, failure)
        (root / "input").mkdir()
        (root / "tools").mkdir()
        env.update(TEST_RUN_STATUS=str(code), TEST_RUN_ERROR=error, TEST_RUN_OUTPUT=output)
        if parent:
            (root / "public").mkdir()
            env.update(REFERENCE=REFERENCE, SOURCE=SOURCE, RECORDS=str(root), WORK=str(root),
                CONTROLLER="sha256:" + "c" * 64)
            # Exercise the actual parent propagation and existing status writer,
            # without invoking acquisition, a provider, or cleanup.
            command = ["bash", "-c", 'source "$1"; if inspect_accounts; then exit 99; fi; status hold',
                "test", str(SCRIPT)]
        else:
            command = ["sh", str(SCRIPT.with_name("inspect_root_accounts.sh")),
                "sha256:" + "c" * 64, str(root / "input"), str(root / "tools"),
                str(root / "inspection"), REFERENCE, SOURCE]
        return subprocess.run(command, env=env, capture_output=True, text=True, timeout=5, check=False)

    def test_failure_classification_reaches_existing_public_status_without_candidate_or_cleanup(self):
        labels = ("input-setup", "layout-validation", "tool-validation", "unpack-launch",
            "unpack-timeout", "unpack-nonzero", "account-projection", "result-serialization")
        cases = [(code, "root image account inspection refused\ncpk-root-account-stage-v1:" + label + "\n",
            "offline-" + label) for code, label in enumerate(labels, 40)]
        cases += [(124, "", "offline-outer-timeout"), (125, "", "offline-outer-execution-failure"),
            (126, "", "offline-outer-execution-failure"), (127, "", "offline-outer-execution-failure"),
            (137, "", "offline-controller-killed-or-timeout"), (17, "private-error-canary", "offline-unknown-controller-failure")]
        for code, error, stage in cases:
            with self.subTest(stage=stage, code=code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                result = self.offline(root, code=code, error=error, parent=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                public = (root / "public" / "status.json").read_text()
                self.assertEqual(json.loads(public)["stage"], stage)
                self.assertEqual(json.loads(public)["inspection"], "hold")
                self.assertNotIn("private-error-canary", public + result.stdout + result.stderr)
                self.assertFalse((root / "inspection" / "account-seal.json").exists())
                self.assertFalse((root / "public" / "account-seal.json").exists())
                events = [json.loads(line) for line in (root / "events").read_text().splitlines()]
                self.assertFalse(any(name == "sudo" for name, args in events))
                self.assertEqual(sum(name == "docker" and args[0] == "run" for name, args in events), 1)

    def test_exit_collision_and_nonexact_marker_remain_unknown(self):
        marker = "root image account inspection refused\ncpk-root-account-stage-v1:layout-validation\n"
        cases = [(41, ""), (40, marker), (17, marker), (41, "private-prefix" + marker),
            (41, marker * 2), (41, marker[:-1]), (41, marker + "private-suffix"),
            (41, "x" * 65536 + marker)]
        for code, error in cases:
            with self.subTest(code=code, size=len(error)), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                result = self.offline(root, code=code, error=error)
                self.assertEqual(result.returncode, 65)
                self.assertNotIn("private-", result.stdout + result.stderr)
                self.assertFalse((root / "inspection" / "account-seal.json").exists())

    def test_success_still_requires_candidate_and_observed_container_absence(self):
        # The transport double emits an opaque receipt. This proves promotion
        # gates only, never successful image inspection or a real account seal.
        for output, failure, promoted in (("", "run", False), ("x" * 4097, "run", False),
                ("synthetic-receipt", "remaining", False), ("synthetic-receipt", "run", True)):
            with self.subTest(size=len(output), failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                result = self.offline(root, code=0, output=output, failure=failure)
                self.assertEqual(result.returncode == 0, promoted)
                seal = root / "inspection" / "account-seal.json"
                self.assertEqual(seal.exists(), promoted)
                if promoted:
                    self.assertEqual(seal.read_text(), output)
