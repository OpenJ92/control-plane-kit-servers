"""Selected root artifacts must observe PID 1's effective UID, not exec's UID."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
ROLE_UIDS = {"cpk-server": "10001", "secrets-server": "10006"}


class RootArtifactProcessUidTests(unittest.TestCase):
    def owner(self):
        spec = importlib.util.spec_from_file_location(
            "root_artifact_inputs", ROOT / "scripts/root_artifact_inputs.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(getattr(module, "require_root_artifact_process_uid", None)),
                        "selected artifact PID 1 effective UID observation is missing")
        return module

    def status(self, effective, *, real="123", saved="456", filesystem="789"):
        return ("Name:\tpython\nState:\tS (sleeping)\nPid:\t1\n"
                f"Uid:\t{real}\t{effective}\t{saved}\t{filesystem}\n"
                "Gid:\t10001\t10001\t10001\t10001\nThreads:\t2\n")

    def rejected(self, owner, role, status):
        with self.assertRaises(owner.RootArtifactError) as caught:
            owner.require_root_artifact_process_uid(role=role, pid1_status=status)
        self.assertEqual(str(caught.exception), "current root artifact input is invalid")
        self.assertNotIn("private-marker", repr(caught.exception))

    def test_each_role_accepts_its_observed_effective_uid(self):
        owner = self.owner()
        for role, uid in ROLE_UIDS.items():
            with self.subTest(role=role):
                self.assertEqual(owner.require_root_artifact_process_uid(
                    role=role, pid1_status=self.status(uid)), uid)

    def test_wrong_effective_uid_refuses_even_when_real_uid_matches(self):
        owner = self.owner()
        for role, uid in ROLE_UIDS.items():
            for wrong in ("10006" if uid == "10001" else "10001", "65534"):
                with self.subTest(role=role, wrong=wrong):
                    self.rejected(owner, role, self.status(wrong, real=uid, saved=uid, filesystem=uid))

    def test_root_effective_uid_refuses(self):
        owner = self.owner()
        for role, uid in ROLE_UIDS.items():
            with self.subTest(role=role):
                self.rejected(owner, role, self.status("0", real=uid, saved=uid, filesystem=uid))

    def test_missing_observation_or_uid_field_refuses(self):
        owner = self.owner()
        for role in ROLE_UIDS:
            for status in (None, "", "Name:\tpython\nPid:\t1\n", "private-marker"):
                with self.subTest(role=role, status=status):
                    self.rejected(owner, role, status)

    def test_malformed_ambiguous_or_unbounded_uid_observation_refuses(self):
        owner = self.owner()
        for role, uid in ROLE_UIDS.items():
            cases = [b"Uid:\t1\t10001\t1\t1\n", {},
                     f"Uid:\t{uid}\n", f"Uid:\t1\t{uid}\t1\n",
                     f"Uid:\t1\t{uid}\t1\t1\t1\n",
                     f"Uid:\t1\t{uid}private-marker\t1\t1\n",
                     f"Uid:\t1\t+{uid}\t1\t1\n",
                     f"Uid:\t1\t0{uid}\t1\t1\n",
                     self.status(uid) + f"Uid:\t1\t{uid}\t1\t1\n",
                     self.status(uid) + "private-marker" * 6000]
            for status in cases:
                with self.subTest(role=role, status=status):
                    self.rejected(owner, role, status)
