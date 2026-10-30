"""Diagnostic command admission only; never acquires images, tools or a mount."""
import os
import json
import re
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/acquire_root_accounts.sh"
REFERENCE = "ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:" + "b" * 64
SOURCE = "a" * 40
RETAINED_REFERENCE = "ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:371b562697a3d1f3ad60c29dd09026133865c0bf19f719c9929b0ca757d93b71"
RETAINED_SOURCE = "3079b70da4207a6a4a2079138e218a9debfc6fd0"
RETAINED_PUBLICATION_RUN = "41001898450"
SUPERSEDED_REFERENCE = "ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:337c8cf44d1ccf624663c866f8084655ead7e8f5c62c121424c9d15f7650e370"
SUPERSEDED_SOURCE = "94ecb34d7d692c23a0ec017fdc0cac984fd9dccf"


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
    if args[0] == "info":
        print(os.environ.get("TEST_DAEMON_PLATFORM", ""))
        print("private-daemon-error-canary", file=sys.stderr)
        sys.exit(int(os.environ.get("TEST_DAEMON_STATUS", "23")))
    if args[0] == "pull":
        print("private-pull-error-canary", file=sys.stderr)
        sys.exit(21)  # Acquisition uncertainty must stop; never simulate a pull.
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
        if "TEST_INSPECT_FILE" in os.environ:
            sys.stdout.buffer.write(pathlib.Path(os.environ["TEST_INSPECT_FILE"]).read_bytes())
            sys.stdout.flush()
            sys.exit(int(os.environ.get("TEST_INSPECT_STATUS", "0")))
        print("{}")  # The metadata controller must not execute in this double.
    else:
        sys.exit(99)
elif name == "git":
    if "rev-parse" in args:
        print(os.environ["TEST_HEAD"])
    elif "status" in args:
        print(os.environ.get("TEST_DIRTY", ""), end="")
    else:
        sys.exit(99)
else:
    sys.exit(99)
'''
        for name in ("docker", "sudo", "findmnt", "id", "skopeo", "git"):
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

    def test_retained_target_requires_distinct_exact_clean_diagnostic_source(self):
        retained = RETAINED_REFERENCE
        producer = RETAINED_SOURCE
        diagnostic = "d" * 40
        cases = (
            ("retained", retained, producer, diagnostic, diagnostic, "", True),
            ("retained", SUPERSEDED_REFERENCE, SUPERSEDED_SOURCE, diagnostic, diagnostic, "", False),
            ("retained", retained, producer, diagnostic, producer, "", False),
            ("retained", retained, producer, diagnostic, diagnostic, " M scripts/example", False),
            ("retained", REFERENCE, producer, diagnostic, diagnostic, "", False),
            ("retained", retained, SOURCE, diagnostic, diagnostic, "", False),
            ("retained", retained, producer, "short", "short", "", False),
            ("same-job", REFERENCE, SOURCE, diagnostic, diagnostic, "", False),
            ("same-job", REFERENCE, SOURCE, SOURCE, SOURCE, "", True),
        )
        for mode, reference, source, selected, head, dirty, admitted in cases:
            with self.subTest(mode=mode, head=head, dirty=bool(dirty), reference=reference), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                env = self.commands(root, "run")
                env.update(MODE=mode, REFERENCE=reference, SOURCE=source, DIAGNOSTIC_SOURCE=selected,
                    TEST_HEAD=head, TEST_DIRTY=dirty, GITHUB_WORKFLOW="publish-product-image", GITHUB_SHA=selected,
                    GITHUB_JOB="inspect-retained-cpk", CPK_INSPECT_RETAINED_CPK="true", CPK_INSPECT_CPK_ACCOUNTS="false")
                result = subprocess.run(["bash", "-c", 'source "$1"; admit_sources', "test", str(SCRIPT)],
                    env=env, capture_output=True, text=True, timeout=5, check=False)
                self.assertEqual(result.returncode == 0, admitted)
                if (root / "events").exists():
                    events = [json.loads(line) for line in (root / "events").read_text().splitlines()]
                    self.assertTrue(all(name == "git" for name, args in events))

    def test_retained_controller_pull_failure_is_one_attempt_with_bounded_public_hold(self):
        for mode in ("same-job", "retained"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                env = self.commands(root, "run")
                (root / "public").mkdir()
                env.update(MODE=mode, REFERENCE=REFERENCE, SOURCE=SOURCE, DIAGNOSTIC_SOURCE="d" * 40,
                    RECORDS=str(root), CONTROLLER="", STAGE="preparation", GITHUB_RUN_ID="123",
                    GITHUB_RUN_ATTEMPT="1", PUBLICATION_RUN=RETAINED_PUBLICATION_RUN)
                result = subprocess.run(["bash", "-c",
                    'source "$1"; if acquire_controller; then exit 0; else status hold; exit 1; fi',
                    "test", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=5, check=False)
                self.assertNotIn("private-pull-error-canary", result.stdout + result.stderr)
                if mode == "same-job":
                    self.assertEqual(result.returncode, 0)
                    self.assertFalse((root / "events").exists())
                else:
                    self.assertNotEqual(result.returncode, 0)
                    public = (root / "public" / "status.json").read_text()
                    status = json.loads(public)
                    self.assertEqual(status["stage"], "controller-acquisition")
                    self.assertEqual(status["inspection"], "hold")
                    self.assertEqual(status["source_revision"], SOURCE)
                    self.assertEqual(status["diagnostic_source_revision"], "d" * 40)
                    self.assertEqual(status["publication_run_id"], RETAINED_PUBLICATION_RUN)
                    self.assertNotIn("private-pull-error-canary", public)
                    events = [json.loads(line) for line in (root / "events").read_text().splitlines()]
                    self.assertEqual(events, [["docker", ["pull", "--quiet", "--platform", "linux/amd64",
                        "docker.io/library/python@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8"]]])
                    self.assertFalse((root / "public" / "account-seal.json").exists())

    def test_retained_preparation_failure_records_prior_publication_without_controller_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = self.commands(root, "run")
            diagnostic = "d" * 40
            env.update(GITHUB_ACTIONS="true", GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="1",
                GITHUB_ACTOR="synthetic", GH_TOKEN="private-token-canary",
                GITHUB_WORKFLOW="publish-product-image", GITHUB_JOB="inspect-retained-cpk", GITHUB_SHA=diagnostic,
                CPK_INSPECT_RETAINED_CPK="true", CPK_INSPECT_CPK_ACCOUNTS="false",
                TEST_HEAD=diagnostic, TEST_DIRTY=" M scripts/example")
            output = root / "output"
            result = subprocess.run(["bash", str(SCRIPT), "--retained", diagnostic,
                RETAINED_REFERENCE, RETAINED_SOURCE, str(output)],
                env=env, capture_output=True, text=True, timeout=5, check=False)
            self.assertNotEqual(result.returncode, 0)
            public = (output / "public" / "status.json").read_text()
            status = json.loads(public)
            self.assertEqual((status["publication"], status["inspection"], status["stage"]),
                ("succeeded", "hold", "preparation"))
            self.assertEqual(status["publication_run_id"], RETAINED_PUBLICATION_RUN)
            provenance = (output / "public" / "provenance.json").read_text()
            self.assertFalse(json.loads(provenance)["source_admitted"])
            self.assertNotIn("private-token-canary", public + provenance + result.stdout + result.stderr)
            events = [json.loads(line) for line in (root / "events").read_text().splitlines()]
            self.assertTrue(all(name in ("id", "git") for name, args in events))
            self.assertFalse((output / "public" / "account-seal.json").exists())

    def test_retained_workflow_selection_and_read_only_job_boundary(self):
        workflow = (SCRIPT.parents[1] / ".github/workflows/publish-product-image.yml").read_text()
        selection = workflow.split("      inspect_retained_cpk:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertIn("        type: boolean\n", selection)
        self.assertIn("        default: false\n", selection)
        # Review the actual job permission/selection declarations. This does not
        # simulate GitHub's scheduler or establish a token's runtime permissions.
        jobs = re.split(r"^  ([a-z-]+):\n", workflow.split("jobs:\n", 1)[1], flags=re.MULTILINE)
        declarations = dict(zip(jobs[1::2], jobs[2::2]))
        self.assertEqual(set(declarations), {"publish", "inspect-retained-cpk"})
        self.assertIn("    if: ${{ !inputs.inspect_retained_cpk }}\n", declarations["publish"])
        diagnostic = declarations["inspect-retained-cpk"]
        self.assertIn("    if: ${{ inputs.inspect_retained_cpk }}\n", diagnostic)
        self.assertIn("    permissions:\n      contents: read\n      packages: read\n", diagnostic)
        self.assertIn("persist-credentials: false", diagnostic)
        for forbidden in ("packages: write", "needs:", "docker/login-action", "publish_product_image.sh", "release_evidence.py"):
            self.assertNotIn(forbidden, diagnostic)
        self.assertIn("CPK_INSPECT_RETAINED_CPK: ${{ inputs.inspect_retained_cpk }}", diagnostic)
        self.assertIn("CPK_INSPECT_CPK_ACCOUNTS: ${{ inputs.inspect_cpk_accounts }}", diagnostic)
        for retained in ("true", "false"):
            for same_job in ("true", "false"):
                with self.subTest(retained=retained, same_job=same_job), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    env = self.commands(root, "run")
                    env.update(MODE="retained", DIAGNOSTIC_SOURCE="d" * 40, TEST_HEAD="d" * 40,
                        SOURCE=RETAINED_SOURCE, REFERENCE=RETAINED_REFERENCE,
                        GITHUB_WORKFLOW="publish-product-image", GITHUB_JOB="inspect-retained-cpk", GITHUB_SHA="d" * 40,
                        CPK_INSPECT_RETAINED_CPK=retained, CPK_INSPECT_CPK_ACCOUNTS=same_job)
                    result = subprocess.run(["bash", "-c", 'source "$1"; admit_sources', "test", str(SCRIPT)],
                        env=env, capture_output=True, text=True, timeout=5, check=False)
                    self.assertEqual(result.returncode == 0, retained == "true" and same_job == "false")

    def test_failed_platform_query_never_admits_matching_output_before_pull(self):
        for platform, code, admitted in (("linux/x86_64", 23, False), ("", 23, False),
                ("windows/amd64", 0, False), ("linux/amd64", 0, True)):
            with self.subTest(platform=platform, code=code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                env = self.commands(root, "run")
                (root / "public").mkdir()
                env.update(MODE="retained", REFERENCE=REFERENCE, SOURCE=SOURCE, RECORDS=str(root),
                    CONTROLLER="", STAGE="preparation", TEST_DAEMON_PLATFORM=platform, TEST_DAEMON_STATUS=str(code))
                result = subprocess.run(["bash", "-c", 'source "$1"; '
                    'if admit_daemon_platform; then if acquire_controller; then exit 99; fi; fi; status hold; exit 1',
                    "test", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=5, check=False)
                self.assertEqual(result.returncode, 1)
                public = (root / "public" / "status.json").read_text()
                self.assertEqual(json.loads(public)["stage"], "controller-acquisition" if admitted else "preparation")
                self.assertNotIn("private-daemon-error-canary", public + result.stdout + result.stderr)
                events = [json.loads(line) for line in (root / "events").read_text().splitlines()]
                self.assertEqual([args[0] for name, args in events], ["info", "pull"] if admitted else ["info"])
                self.assertTrue(all(name == "docker" for name, args in events))
                self.assertFalse((root / "public" / "account-seal.json").exists())

    def test_raw_config_capture_preserves_bounded_bytes_and_producer_failure(self):
        raw = b'{"config":{"Env":["private-config-canary"]}}'
        for content, producer_status, accepted in ((raw, 0, True), (raw, 23, False),
                (b"", 0, False), (b"x" * (1024 * 1024 + 1), 0, False)):
            with self.subTest(size=len(content), producer_status=producer_status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                env = self.commands(root, "run")
                work = root / "work"
                work.mkdir()
                supplied = root / "supplied-config"
                supplied.write_bytes(content)
                env.update(WORK=str(work), REFERENCE=REFERENCE, TEST_INSPECT_FILE=str(supplied),
                    TEST_INSPECT_STATUS=str(producer_status))
                result = subprocess.run(["bash", "-c", 'source "$1"; AUTH="$WORK/auth.json"; '
                    'capture_metadata "$REFERENCE" "$WORK/source-config.json" config', "test", str(SCRIPT)],
                    env=env, capture_output=True, text=True, timeout=5, check=False)
                self.assertEqual(result.returncode == 0, accepted)
                self.assertNotIn("private-config-canary", result.stdout + result.stderr)
                self.assertEqual(result.stdout, "")
                if accepted:
                    self.assertEqual((work / "source-config.json").read_bytes(), content)
                events = [json.loads(line) for line in (root / "events").read_text().splitlines()]
                self.assertEqual(len(events), 1)
                name, args = events[0]
                self.assertEqual(name, "skopeo")
                self.assertIn("--raw", args)
                self.assertIn("--config", args)
                self.assertEqual(args[args.index("--retry-times") + 1], "0")
                self.assertEqual(args[-1], "docker://" + REFERENCE)
