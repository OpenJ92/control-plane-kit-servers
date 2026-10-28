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
        sys.exit(23 if failure == "docker" else 0)
    if args[0] == "image":
        print("linux/amd64" if args[-1] == "{{.Os}}/{{.Architecture}}" else "sha256:" + "c" * 64)
    elif args[0] == "run":
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
