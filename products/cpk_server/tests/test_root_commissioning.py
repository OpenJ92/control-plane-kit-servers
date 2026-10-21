"""Offline first-root commissioning laws; keys exist only in Docker test custody."""
from contextlib import ExitStack
import copy
import fcntl
from hashlib import sha256
import importlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from control_plane_kit_core.configuration import ConfigurationArtifact


PREPARER = "sha256:" + "a" * 64
MODULE = "control_plane_kit_servers_cpk_server.root_commissioning"
PURPOSE_FILES = {
    "workload-node-control-surface-read": "surface-read.pem",
    "workload-node-health-read": "health-read.pem",
}
MODES = {"lock": 0o600, "intent.json": 0o600, "receivers.json": 0o600,
         "surface-read.pem": 0o400, "health-read.pem": 0o400,
         "public.json": 0o600, "complete.json": 0o600}


def intent(state):
    return {"schema": "cpk.root-commissioning.intent.v1",
            "installation_id": "fixture-root", "workspace_id": "fixture-workspace",
            "profile": "operator-offline-read-trust",
            "custody": {"host_directory": str(state), "uid": os.geteuid(), "gid": os.getegid()}}


def snapshot(state):
    return {path.name: (path.read_bytes(), path.stat().st_mtime_ns,
                       stat.S_IMODE(path.stat().st_mode)) for path in state.iterdir()}


class RootCommissioningTests(unittest.TestCase):
    def api(self):
        try:
            module = importlib.import_module(MODULE)
        except ModuleNotFoundError as error:
            if error.name != MODULE:
                raise
            self.fail("root commissioning public interface is not implemented")
        bootstrap = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")
        self.error, self.hold = bootstrap.RootBootstrapError, bootstrap.RootBootstrapHold
        return module

    def custody(self):
        # The owning Docker image's /app is private from foreign writers; /tmp
        # is deliberately not used as an example of approved host ancestry.
        directory = self.enterContext(TemporaryDirectory(dir=Path.cwd()))
        state = Path(directory) / "commissioning"
        state.mkdir(mode=0o700)
        return state

    def planned(self, api, state):
        return api.plan_root_commissioning(intent(state), preparer_image_id=PREPARER)

    def prepare(self, api, state, plan=None):
        plan = self.planned(api, state) if plan is None else plan
        return api.prepare_root_commissioning(plan, expected_digest=plan["digest"],
            preparer_image_id=PREPARER, state_directory=state)

    def no_generation(self):
        stack = ExitStack()
        allocate = stack.enter_context(patch("uuid.uuid4", side_effect=AssertionError("identity allocated")))
        generate = stack.enter_context(patch.object(Ed25519PrivateKey, "generate",
                                                   side_effect=AssertionError("key generated")))
        # A bounded implementation may catch AssertionError: verify calls too.
        stack.callback(allocate.assert_not_called)
        stack.callback(generate.assert_not_called)
        return stack

    def test_plan_is_pure_deterministic_and_binds_exact_intent_and_image(self):
        api, state = self.api(), self.custody()
        document = intent(state)
        with self.no_generation(), patch("builtins.open", side_effect=AssertionError("file opened")), \
                patch("os.open", side_effect=AssertionError("file opened")), \
                patch("socket.socket", side_effect=AssertionError("network opened")):
            plan = api.plan_root_commissioning(document, preparer_image_id=PREPARER)
            self.assertEqual(plan, api.plan_root_commissioning(document, preparer_image_id=PREPARER))
        self.assertEqual(plan["schema"], "cpk.root-commissioning.plan.v1")
        self.assertEqual(plan["input"], document)
        self.assertEqual(plan["preparer_image_id"], PREPARER)
        self.assertEqual(set(plan["issuers"]), set(PURPOSE_FILES))
        self.assertEqual(len(set(plan["issuers"].values())), 2)
        self.assertNotIn("receiver_ids", plan)
        self.assertFalse(list(state.iterdir()))
        for field, value in (("installation_id", "other-root"), ("workspace_id", "other-workspace")):
            changed = copy.deepcopy(document)
            changed[field] = value
            self.assertNotEqual(plan["digest"], api.plan_root_commissioning(
                changed, preparer_image_id=PREPARER)["digest"])
        self.assertNotEqual(plan["digest"], api.plan_root_commissioning(
            document, preparer_image_id="sha256:" + "b" * 64)["digest"])

    def test_intent_is_closed_bounded_and_has_no_implicit_authority(self):
        api, state = self.api(), self.custody()
        candidates = []
        for field in intent(state):
            changed = intent(state)
            del changed[field]
            candidates.append(changed)
        for field, value in (("profile", "managed"), ("installation_id", "x" * 65537),
                             ("provider_token", "private-canary"), ("purposes", ["workload-node-control"])):
            changed = intent(state)
            changed[field] = value
            candidates.append(changed)
        for field, value in (("host_directory", "relative"), ("host_directory", "/a/../b"),
                             ("uid", True), ("gid", -1), ("extra", "private-canary")):
            changed = intent(state)
            changed["custody"][field] = value
            candidates.append(changed)
        for candidate in candidates:
            with self.subTest(candidate=list(candidate)), self.no_generation(), self.assertRaises(self.error) as caught:
                api.plan_root_commissioning(candidate, preparer_image_id=PREPARER)
            self.assertNotIn("private-canary", str(caught.exception))
            self.assertLess(len(str(caught.exception)), 256)

    def test_saved_plan_image_digest_and_destination_drift_refuse_before_writes(self):
        api, state = self.api(), self.custody()
        plan = self.planned(api, state)
        altered = copy.deepcopy(plan)
        altered["input"]["workspace_id"] = "substituted"
        for candidate, digest, image, destination in (
            (altered, plan["digest"], PREPARER, state),
            (plan, "0" * 64, PREPARER, state),
            (plan, plan["digest"], "sha256:" + "b" * 64, state),
            (plan, plan["digest"], PREPARER, state.parent),
        ):
            with self.subTest(image=image, destination=destination.name), self.no_generation(), self.assertRaises(self.error):
                api.prepare_root_commissioning(candidate, expected_digest=digest,
                    preparer_image_id=image, state_directory=destination)
            self.assertFalse(list(state.iterdir()))

    def test_real_product_artifacts_have_exact_targets_and_two_shared_public_families(self):
        api, state = self.api(), self.custody()
        result = self.prepare(api, state)
        from control_plane_kit_servers_cpk_server.control_configuration import (
            cpk_control_configuration_artifact, cpk_control_declaration, decode_cpk_control_configuration)
        from control_plane_kit_servers_secrets_server.configuration import secrets_control_configuration_artifact
        from control_plane_kit_secrets.control import decode_secrets_control_configuration, secrets_control_declaration
        self.assertEqual(result["schema"], "cpk.root-commissioning.public.v1")
        self.assertEqual(result["intent_digest"], self.planned(api, state)["digest"])
        self.assertEqual(result["completion_file"], "complete.json")
        self.assertEqual(set(result["artifacts"]), {"cpk", "secrets"})
        self.assertEqual(set(result["receiver_ids"]), {"cpk", "secrets"})
        self.assertEqual(len(set(result["receiver_ids"].values())), 2)
        families = []
        for role, socket, decode, factory, declaration in (
            ("cpk", "http-api", decode_cpk_control_configuration, cpk_control_configuration_artifact, cpk_control_declaration),
            ("secrets", "control", decode_secrets_control_configuration, secrets_control_configuration_artifact, secrets_control_declaration),
        ):
            artifact = ConfigurationArtifact.from_descriptor(result["artifacts"][role])
            configuration = decode(artifact.content.encode())
            self.assertEqual(factory(configuration).descriptor(), artifact.descriptor())
            self.assertEqual(configuration.declaration, declaration())
            self.assertEqual(configuration.target.workspace_id.value, "fixture-workspace")
            self.assertEqual(configuration.target.runtime_id.value, "fixture-root-docker")
            self.assertEqual(configuration.target.node_id.value, "fixture-root-" + role)
            self.assertEqual(configuration.target.provider_socket_name.value, socket)
            self.assertEqual(configuration.target.receiver_id, result["receiver_ids"][role])
            self.assertRegex(configuration.target.receiver_id, r"^[0-9a-f]{32}$")
            self.assertEqual({family.purpose.value for family in configuration.verifiers}, set(PURPOSE_FILES))
            families.append(configuration.verifiers)
            for family in configuration.verifiers:
                public, = family.public_keys
                private = serialization.load_pem_private_key((state / PURPOSE_FILES[family.purpose.value]).read_bytes(), None)
                self.assertIsInstance(private, Ed25519PrivateKey)
                expected = private.public_key().public_bytes(serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo).decode()
                self.assertEqual(public.public_key_pem, expected)
                self.assertEqual(result["public_keys"][family.purpose.value], {
                    "issuer": family.issuer, "key_id": public.key_id,
                    "public_key_sha256": sha256(expected.encode()).hexdigest()})
        self.assertEqual(families[0], families[1])
        self.assertNotEqual((state / "surface-read.pem").read_bytes(), (state / "health-read.pem").read_bytes())

    def test_durable_layout_is_exact_private_and_has_no_private_bytes_or_digests_in_public_records(self):
        api, state = self.api(), self.custody()
        result = self.prepare(api, state)
        self.assertEqual({p.name for p in state.iterdir()}, set(MODES))
        for name, mode in MODES.items():
            info = (state / name).stat()
            self.assertEqual(stat.S_IMODE(info.st_mode), mode)
            self.assertEqual((info.st_uid, info.st_gid), (os.geteuid(), os.getegid()))
            self.assertLessEqual(info.st_size, 4096 if name.endswith(".pem") else 65536)
        self.assertEqual(json.loads((state / "public.json").read_bytes()), result)
        public = json.dumps(result).encode() + b"".join((state / name).read_bytes()
            for name in ("intent.json", "receivers.json", "public.json", "complete.json"))
        for name in PURPOSE_FILES.values():
            private = (state / name).read_bytes()
            self.assertNotIn(private, public)
            self.assertNotIn(sha256(private).hexdigest().encode(), public)
        self.assertNotIn(b"PRIVATE KEY", public)

    def test_ids_are_persisted_independently_before_key_generation(self):
        api, state = self.api(), self.custody()
        import uuid
        allocate, generate = uuid.uuid4, Ed25519PrivateKey.generate
        allocations, generations, persisted = [], [], []
        real_fsync = os.fsync
        def persist_checked(fd):
            real_fsync(fd)
            persisted.append(os.readlink(f"/proc/self/fd/{fd}"))
        def assert_durable_entry(name):
            self.assertIn(str(state / name), persisted)
            file_position = len(persisted) - 1 - persisted[::-1].index(str(state / name))
            self.assertIn(str(state), persisted[file_position + 1:],
                          "directory entry must be durable before allocation/generation")
        def allocate_checked():
            self.assertTrue((state / "intent.json").is_file())
            assert_durable_entry("intent.json")
            self.assertFalse(any((state / name).exists() for name in PURPOSE_FILES.values()))
            value = allocate()
            allocations.append(value.hex)
            return value
        def generate_checked():
            saved = (state / "receivers.json").read_text()
            assert_durable_entry("receivers.json")
            self.assertEqual(len(allocations), 2)
            for receiver in allocations:
                self.assertIn(receiver, saved)
            generations.append(True)
            return generate()
        with patch("os.fsync", side_effect=persist_checked), patch("uuid.uuid4", side_effect=allocate_checked), \
                patch.object(Ed25519PrivateKey, "generate", side_effect=generate_checked):
            result = self.prepare(api, state)
        self.assertEqual(set(result["receiver_ids"].values()), set(allocations))
        self.assertEqual(len(generations), 2)

    def test_pre_generation_directory_sync_failure_preserves_marker_and_holds_retry(self):
        api = self.api()
        import uuid
        real_allocate, real_fsync = uuid.uuid4, os.fsync
        for stop in ("intent.json", "receivers.json"):
            state = self.custody()
            reached = []
            def fail_directory_sync(fd):
                if os.readlink(f"/proc/self/fd/{fd}") == str(state) and (state / stop).exists():
                    reached.append(stop)
                    raise OSError("private-canary directory persistence failure")
                real_fsync(fd)
            with self.subTest(stop=stop), patch("os.fsync", side_effect=fail_directory_sync), \
                    patch("uuid.uuid4", wraps=real_allocate) as allocate, \
                    patch.object(Ed25519PrivateKey, "generate", side_effect=AssertionError("premature key")) as generate:
                with self.assertRaises(self.hold):
                    self.prepare(api, state)
                self.assertEqual(reached, [stop])
                self.assertEqual(allocate.call_count, 0 if stop == "intent.json" else 2)
                generate.assert_not_called()
            self.assertTrue((state / "intent.json").exists())
            self.assertFalse((state / "complete.json").exists())
            self.assertFalse(any((state / name).exists() for name in PURPOSE_FILES.values()))
            before = snapshot(state)
            with self.no_generation(), self.assertRaises(self.hold):
                self.prepare(api, state)
            self.assertEqual(snapshot(state), before)

    def test_completion_is_persisted_after_all_inputs_and_directory_sync_follows_rename(self):
        api, state = self.api(), self.custody()
        real_fsync, persisted = os.fsync, []
        def observe(fd):
            name = os.readlink(f"/proc/self/fd/{fd}")
            if name == str(state / "complete.new"):
                for required in ("intent.json", "receivers.json", "surface-read.pem", "health-read.pem", "public.json"):
                    self.assertIn(str(state / required), persisted)
                self.assertFalse((state / "complete.json").exists())
            real_fsync(fd)
            persisted.append(name)
            if name == str(state) and (state / "complete.json").exists():
                persisted.append("completed-directory")
        with patch("os.fsync", side_effect=observe):
            self.prepare(api, state)
        self.assertIn(str(state / "complete.new"), persisted)
        self.assertEqual(persisted[-1], "completed-directory")
        self.assertFalse((state / "complete.new").exists())

    def test_complete_reuse_preserves_ids_keys_and_every_file_byte_and_mtime(self):
        api, state = self.api(), self.custody()
        result = self.prepare(api, state)
        before = snapshot(state)
        with self.no_generation():
            self.assertEqual(self.prepare(api, state), result)
        self.assertEqual(snapshot(state), before)

    def test_changed_completed_intent_is_a_hold_without_rewriting(self):
        api, state = self.api(), self.custody()
        self.prepare(api, state)
        before = snapshot(state)
        for field in ("installation_id", "workspace_id"):
            changed = intent(state)
            changed[field] = "other-scope"
            plan = api.plan_root_commissioning(changed, preparer_image_id=PREPARER)
            with self.no_generation(), self.assertRaises(self.hold):
                self.prepare(api, state, plan)
            self.assertEqual(snapshot(state), before)

    def test_pristine_lock_only_state_can_complete(self):
        api, state = self.api(), self.custody()
        (state / "lock").touch(mode=0o600)
        self.prepare(api, state)
        self.assertTrue((state / "complete.json").is_file())

    def test_same_directory_contention_holds_without_identity_allocation(self):
        api, state = self.api(), self.custody()
        lock = os.open(state / "lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.no_generation(), self.assertRaises(self.hold):
                self.prepare(api, state)
            self.assertEqual({p.name for p in state.iterdir()}, {"lock"})
        finally:
            os.close(lock)

    def test_incomplete_unknown_or_completion_temporary_entries_hold_unchanged(self):
        api = self.api()
        for name in ("intent.json", "receivers.json", "surface-read.pem", "public.json", "complete.new", "unknown"):
            state = self.custody()
            (state / name).write_bytes(b"private-canary")
            (state / name).chmod(0o600)
            before = snapshot(state)
            with self.subTest(name=name), self.no_generation(), self.assertRaises(self.hold) as caught:
                self.prepare(api, state)
            self.assertNotIn("private-canary", str(caught.exception))
            self.assertEqual(snapshot(state), before)

    def test_wrong_effective_uid_or_gid_refuses_before_writes(self):
        api, state = self.api(), self.custody()
        plan = self.planned(api, state)
        for name in ("geteuid", "getegid"):
            actual = getattr(os, name)()
            with self.subTest(identity=name), patch("os." + name, return_value=actual + 1), \
                    self.no_generation(), self.assertRaises(self.hold):
                self.prepare(api, state, plan)
            self.assertFalse(list(state.iterdir()))

    def test_unsafe_directory_or_lock_modes_and_symlinks_refuse(self):
        api = self.api()
        for fault in ("directory-mode", "directory-link", "lock-mode", "lock-link"):
            state = self.custody()
            destination = state
            if fault == "directory-mode":
                state.chmod(0o755)
            elif fault == "directory-link":
                destination = state.parent / "alias"
                destination.symlink_to(state, target_is_directory=True)
            elif fault == "lock-mode":
                (state / "lock").touch(mode=0o644)
            else:
                outside = state.parent / "outside"
                outside.write_bytes(b"untouched")
                (state / "lock").symlink_to(outside)
            with self.subTest(fault=fault), self.no_generation(), self.assertRaises(self.hold):
                self.prepare(api, destination)
            self.assertFalse((state / "intent.json").exists())
            if fault == "lock-link":
                self.assertEqual(outside.read_bytes(), b"untouched")

    def test_completed_missing_mode_unknown_or_link_drift_holds(self):
        api = self.api()
        for fault in ("missing-key", "key-mode", "unknown", "key-link", "intent", "receivers", "public", "completion"):
            state = self.custody()
            self.prepare(api, state)
            key = state / "health-read.pem"
            if fault == "missing-key":
                key.unlink()
            elif fault == "key-mode":
                key.chmod(0o600)
            elif fault == "unknown":
                (state / "unknown").write_text("unclaimed")
            elif fault == "key-link":
                key.rename(state.parent / "outside-key")
                key.symlink_to(state.parent / "outside-key")
            else:
                name = {"intent": "intent.json", "receivers": "receivers.json",
                        "public": "public.json", "completion": "complete.json"}[fault]
                (state / name).write_text("{}")
            with self.subTest(fault=fault), self.no_generation(), self.assertRaises(self.hold):
                self.prepare(api, state)

    def test_foreign_directory_and_private_file_ownership_hold(self):
        api = self.api()
        # The owning unit image is root; chown affects only disposable fixtures.
        self.assertEqual(os.geteuid(), 0, "owning Docker unit image identity changed")
        for fault in ("directory", "key-owner", "key-group"):
            state = self.custody()
            if fault != "directory":
                self.prepare(api, state)
            path = state if fault == "directory" else state / "health-read.pem"
            os.chown(path, 10001 if fault != "key-group" else 0, 10001 if fault == "key-group" else os.getegid())
            try:
                with self.subTest(fault=fault), self.no_generation(), self.assertRaises(self.hold):
                    self.prepare(api, state)
            finally:
                os.chown(path, os.geteuid(), os.getegid())

    def test_own_private_public_mismatch_and_corrupt_private_payload_are_detached_holds(self):
        api = self.api()
        for fault in ("different-key", "invalid", "oversized"):
            state = self.custody()
            self.prepare(api, state)
            key = state / "health-read.pem"
            payload = b"private-canary" * (400 if fault == "oversized" else 1)
            if fault == "different-key":
                payload = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            key.chmod(0o600)
            key.write_bytes(payload)
            key.chmod(0o400)
            before = snapshot(state)
            with self.subTest(fault=fault), self.no_generation(), self.assertRaises(self.hold) as caught:
                self.prepare(api, state)
            error = caught.exception
            self.assertIsNone(error.__context__)
            self.assertIsNone(error.__cause__)
            self.assertNotIn("private-canary", repr(error))
            self.assertLess(len(str(error)), 256)
            self.assertEqual(snapshot(state), before)

    def test_each_durable_write_interruption_preserves_incomplete_state_and_forbids_retry(self):
        api = self.api()
        real_fsync = os.fsync
        for stop in ("intent.json", "receivers.json", "surface-read.pem", "health-read.pem", "public.json", "complete.new"):
            state = self.custody()
            reached = []
            def fail_after_persist(fd):
                real_fsync(fd)
                # Linux /proc is the owning Docker runtime's descriptor view.
                if os.readlink(f"/proc/self/fd/{fd}") == str(state / stop):
                    reached.append(stop)
                    raise OSError("private-canary persistence failure")
            with self.subTest(stop=stop), patch("os.fsync", side_effect=fail_after_persist), self.assertRaises(self.hold) as caught:
                self.prepare(api, state)
            self.assertEqual(reached, [stop], "failure must reach the actual file persistence boundary")
            self.assertNotIn("private-canary", str(caught.exception))
            self.assertTrue((state / "intent.json").exists())
            self.assertFalse((state / "complete.json").exists())
            before = snapshot(state)
            with self.no_generation(), self.assertRaises(self.hold):
                self.prepare(api, state)
            self.assertEqual(snapshot(state), before)

    def test_cli_plan_and_prepare_return_only_public_results(self):
        api, state = self.api(), self.custody()
        input_path, plan_path = state.parent / "input.json", state.parent / "plan.json"
        input_path.write_text(json.dumps(intent(state)))
        input_path.chmod(0o600)
        planned = subprocess.run([sys.executable, "-m", MODULE, "plan", "--input", str(input_path),
            "--preparer", PREPARER], capture_output=True, check=False)
        self.assertEqual(planned.returncode, 0, "commissioning plan CLI failed")
        plan = json.loads(planned.stdout)
        self.assertEqual(plan, self.planned(api, state))
        plan_path.write_bytes(planned.stdout)
        plan_path.chmod(0o600)
        prepared = subprocess.run([sys.executable, "-m", MODULE, "prepare", "--plan", str(plan_path),
            "--digest", plan["digest"], "--preparer", PREPARER, "--state", str(state)], capture_output=True, check=False)
        self.assertEqual(prepared.returncode, 0, "commissioning prepare CLI failed")
        self.assertEqual(json.loads(prepared.stdout), json.loads((state / "public.json").read_bytes()))
        self.assertNotIn(b"PRIVATE KEY", prepared.stdout + prepared.stderr)

    def test_mapped_cli_binds_approved_host_state_and_refuses_mismatch_before_writes(self):
        api, state = self.api(), self.custody()
        approved_host = state.parent / "host-only-commissioning"
        plan = self.planned(api, approved_host)
        plan_path = state.parent / "mapped-plan.json"
        plan_path.write_text(json.dumps(plan))
        plan_path.chmod(0o600)
        command = [sys.executable, "-m", MODULE, "prepare", "--plan", str(plan_path),
            "--digest", plan["digest"], "--preparer", PREPARER, "--state", str(state), "--host-state"]
        refused = subprocess.run(command + [str(state.parent / "wrong-host")], capture_output=True, check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertFalse(list(state.iterdir()))
        # The library has no implicit mapping exception to its exact-path law.
        with self.no_generation(), self.assertRaises(self.error):
            self.prepare(api, state, plan)
        self.assertFalse(list(state.iterdir()))
        prepared = subprocess.run(command + [str(approved_host)], capture_output=True, check=False)
        self.assertEqual(prepared.returncode, 0, "mapped commissioning CLI failed")
        result = json.loads(prepared.stdout)
        self.assertEqual(result["intent_digest"], plan["digest"])
        self.assertEqual(result, json.loads((state / "public.json").read_bytes()))
        self.assertFalse(approved_host.exists(), "container CLI must not open the host namespace path")
        self.assertNotIn(b"PRIVATE KEY", prepared.stdout + prepared.stderr + refused.stdout + refused.stderr)
        before = snapshot(state)
        repeated = subprocess.run(command + [str(approved_host)], capture_output=True, check=False)
        self.assertEqual(repeated.returncode, 0, "mapped exact reuse failed")
        self.assertEqual(json.loads(repeated.stdout), result)
        self.assertEqual(snapshot(state), before)

    def launcher(self, state, action, *arguments):
        """Execute the real shell launcher; replace only the Docker CLI boundary."""
        tools = state.parent / "tools"
        tools.mkdir(exist_ok=True)
        log = state.parent / "docker-calls.jsonl"
        docker = tools / "docker"
        docker.write_text("#!" + sys.executable + "\n" + '''
import json, os, sys
with open(os.environ["COMMISSION_TEST_CALLS"], "a") as output:
    output.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1:3] == ["image", "inspect"]:
    print(sys.argv[-1])
elif sys.argv[1] == "run":
    print("{}")
else:
    raise SystemExit(9)
''')
        docker.chmod(0o700)
        environment = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                           COMMISSION_TEST_CALLS=str(log))
        root = Path(__file__).resolve().parents[3]
        process = subprocess.run(["sh", str(root / "bootstrap.sh"), action, PREPARER, *map(str, arguments)],
            env=environment, capture_output=True, check=False)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return process, [call for call in calls if call[0] == "run"]

    def test_launcher_commission_prepare_has_only_exact_plan_and_custody_mounts(self):
        api, state = self.api(), self.custody()
        plan = self.planned(api, state)
        path = state.parent / "plan.json"
        path.write_text(json.dumps(plan))
        path.chmod(0o600)
        process, runs = self.launcher(state, "commission-prepare", path, plan["digest"], state)
        self.assertEqual(process.returncode, 0, "commission-prepare launcher is unavailable")
        self.assertEqual(len(runs), 1)
        command, = runs
        self.assertEqual(command[command.index("--user") + 1], f"{os.geteuid()}:{os.getegid()}")
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertIn("--read-only", command)
        self.assertIn("ALL", command)
        self.assertIn("no-new-privileges", command)
        mounts = [command[index + 1] for index, value in enumerate(command) if value == "--mount"]
        self.assertEqual(set(mounts), {f"type=bind,source={path},target=/bootstrap/plan.json,readonly",
                                      f"type=bind,source={state},target=/commissioning"})
        self.assertIn(MODULE, command)
        self.assertEqual(command[command.index("--host-state") + 1], str(state))
        self.assertNotIn("/var/run/docker.sock", " ".join(command))

    def test_launcher_refuses_unsafe_parent_without_chmod_or_container_execution(self):
        api = self.api()
        for fault in ("writable", "symlink"):
            state = self.custody()
            parent = state.parent / "parent"
            parent.mkdir(mode=0o700)
            destination = parent / "commissioning"
            if fault == "writable":
                parent.chmod(0o777)
            else:
                alias = state.parent / "alias"
                alias.symlink_to(parent, target_is_directory=True)
                destination = alias / "commissioning"
            document = intent(destination)
            plan = api.plan_root_commissioning(document, preparer_image_id=PREPARER)
            path = state.parent / "plan.json"
            path.write_text(json.dumps(plan))
            path.chmod(0o600)
            previous_mode = stat.S_IMODE(parent.stat().st_mode)
            process, runs = self.launcher(state, "commission-prepare", path, plan["digest"], destination)
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(runs)
            self.assertFalse(destination.exists())
            self.assertEqual(stat.S_IMODE(parent.stat().st_mode), previous_mode)


class RootCommissioningCoordinateTests(unittest.TestCase):
    def test_bootstrap_driver_secrets_pin_is_a_generated_destination(self):
        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location("commissioning_coordinates", root / "scripts/apply_coordinates.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        coordinates = module.load_coordinates(module.COORDINATES)
        original = module.generate_updates(coordinates)
        destination = root / "products/cpk_server/Dockerfile.bootstrap"
        self.assertIn(destination, original, "bootstrap dependency destination omitted from generation")
        changed = copy.deepcopy(coordinates)
        changed["upstreams"]["control_plane_kit_secrets_commit"] = "f" * 40
        generated = module.generate_updates(changed)
        old = coordinates["upstreams"]["control_plane_kit_secrets_commit"].encode()
        self.assertIn(old, original[destination])
        self.assertEqual(generated[destination], original[destination].replace(old, b"f" * 40))
        for path, content in original.items():
            if path.suffix == ".json":
                self.assertEqual(generated[path], content)


if __name__ == "__main__":
    unittest.main()
