"""Archive schema ownership and pre-helper initialization diagnostics."""

import base64
import hashlib
from importlib.metadata import PathDistribution
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_servers_cpk_server import bootstrap
from control_plane_kit_servers_cpk_server import bootstrap_initialization as owner
from control_plane_kit_servers_cpk_server import bootstrap_initialization_runtime as runtime


class ArchiveSchemaOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.site = Path(self.enterContext(TemporaryDirectory()))
        self.relative = Path("control_plane_kit_operations/postgres/current_schema.sql")
        self.schema = self.site / self.relative
        self.schema.parent.mkdir(parents=True)
        self.schema.write_bytes(b"SELECT 1;\n")
        self.digest = hashlib.sha256(self.schema.read_bytes())
        encoded = base64.urlsafe_b64encode(self.digest.digest()).decode("ascii").rstrip("=")
        self.row = f"{self.relative},sha256={encoded},{self.schema.stat().st_size}\n"
        metadata = self.site / "control_plane_kit_operations-1.dist-info"
        metadata.mkdir()
        self.record = metadata / "RECORD"
        self.record.write_text(self.row)
        self.origin = metadata / "direct_url.json"
        self.commit = "a" * 40
        self.origin.write_text(json.dumps({
            "url": f"https://github.com/OpenJ92/control-plane-kit/archive/{self.commit}.zip",
            "subdirectory": "control-plane-kit-operations",
        }))
        self.enterContext(patch.object(owner, "distribution", return_value=PathDistribution(metadata)))
        self.enterContext(patch.object(owner, "files", side_effect=self.resource_directory))

    def resource_directory(self, package):
        return self.site.joinpath(*package.split("."))

    def assert_schema_refused(self):
        with self.assertRaises(bootstrap.RootBootstrapError) as caught:
            owner.package_correlation()
        failure = bootstrap.bootstrap_failure(caught.exception)
        self.assertEqual((failure["stage"], failure["reason"]),
                         ("initialization-target", "schema-owner-unverified"))

    def test_archive_returns_existing_commit_and_sql_digest(self):
        self.assertEqual(owner.package_correlation(),
                         {"operations_commit": self.commit, "schema_sha256": self.digest.hexdigest()})

    def test_schema_requires_one_matching_sha256_record(self):
        for name, rows in {
            "absent": "other.sql,,\n",
            "duplicate": self.row * 2,
            "unhashed": f"{self.relative},,\n",
            "wrong algorithm": self.row.replace("sha256=", "sha512="),
            "wrong digest": f"{self.relative},sha256=unrelated,\n",
        }.items():
            with self.subTest(record=name):
                self.record.write_text(rows)
                self.assert_schema_refused()

    def test_changed_sql_and_same_byte_shadow_are_refused(self):
        original = self.schema.read_bytes()
        self.schema.write_bytes(b"SELECT 2;\n")
        self.assert_schema_refused()
        self.schema.write_bytes(original)
        shadow = self.site / "shadow" / self.relative
        shadow.parent.mkdir(parents=True)
        shadow.write_bytes(original)
        with patch.object(owner, "files", side_effect=lambda name: self.site.joinpath("shadow", *name.split("."))):
            self.assert_schema_refused()

    def test_local_directory_remains_outside_archive_contract(self):
        self.origin.write_text(json.dumps({"url": "file:///opt/cpk-bootstrap-driver-build/operations", "dir_info": {}}))
        self.assert_schema_refused()


class InitializationTargetDiagnosticsTests(unittest.TestCase):
    def test_target_and_schema_refusals_precede_helper_intent(self):
        plan = {"postgres_node_id": "pg", "digest": "plan", "driver_image_id": "driver"}
        for cause, reason in (("engine", "initialization-target-refused"),
                              ("schema", "schema-owner-unverified")):
            with self.subTest(cause=cause):
                receipt = {"phase": "acquiring", "pending": None, "resources": {"containers": {"pg": {"id": "pg"}}},
                           "plan_digest": "plan", "driver_image_id": "driver", "engine_id": "expected-engine"}
                client, sdk = Mock(), Mock()
                client.info.return_value = {"ID": "different-engine"}
                with patch.object(owner, "distribution", side_effect=OSError("private-path-canary")) as dist:
                    with self.assertRaises(bootstrap.RootBootstrapError) as caught:
                        if cause == "schema":
                            # The target's earlier ownership observations succeeded.
                            with patch.object(runtime, "_target", side_effect=lambda *_: owner.package_correlation()):
                                runtime.initialize_acquired_workspace(plan, {}, None, Path("/unused"), receipt, client, sdk)
                        else:
                            runtime.initialize_acquired_workspace(plan, {}, None, Path("/unused"), receipt, client, sdk)
                    self.assertEqual(dist.call_count, int(cause == "schema"))
                observed = bootstrap.bootstrap_failure(caught.exception)
                self.assertEqual((observed["stage"], observed["reason"]), ("initialization-target", reason))
                self.assertNotIn("private-path-canary", json.dumps(observed))
                self.assertNotIn("initialization_helper", receipt)
                self.assertIsNone(receipt["pending"])
                client.volumes.create.assert_not_called()
                client.containers.create.assert_not_called()
