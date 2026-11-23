"""Archive schema ownership and pre-helper initialization diagnostics."""

import base64
import hashlib
from importlib.metadata import PathDistribution
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_servers_cpk_server import bootstrap
from control_plane_kit_servers_cpk_server import bootstrap_initialization as owner
from control_plane_kit_servers_cpk_server import bootstrap_initialization_runtime as runtime
from workspace_initialization_fixtures import initialization_inputs


class ArchiveSchemaOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.site = Path(self.enterContext(TemporaryDirectory()))
        self.relative = Path("control_plane_kit_operations/postgres/current_schema.sql")
        self.schema = self.site / self.relative
        self.schema.parent.mkdir(parents=True)
        metadata = self.site / "control_plane_kit_operations-1.dist-info"
        metadata.mkdir()
        self.record = metadata / "RECORD"
        self.install_schema(b"SELECT 1;\n")
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

    def install_schema(self, content, *, include_size=True):
        self.schema.write_bytes(content)
        self.digest = hashlib.sha256(content)
        encoded = base64.urlsafe_b64encode(self.digest.digest()).decode("ascii").rstrip("=")
        size = str(len(content)) if include_size else ""
        self.row = f"{self.relative},sha256={encoded},{size}\n"
        self.record.write_text(self.row)

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

    def test_changed_sql_is_refused(self):
        self.schema.write_bytes(b"SELECT 2;\n")
        self.assert_schema_refused()

    def test_correct_digest_with_inconsistent_record_size_is_refused(self):
        entry, _ = self.row.rsplit(",", 1)
        self.record.write_text(f"{entry},{self.schema.stat().st_size + 1}\n")
        self.assert_schema_refused()

    def test_empty_schema_cannot_be_satisfied_by_a_nonregular_descriptor(self):
        self.install_schema(b"")
        open_file = os.open
        blocking_modes = []

        def open_with_device_at_schema(path, flags, *args, **kwargs):
            # /dev/null is immediately readable and has the same size and bytes.
            # Only the type of the opened object distinguishes it.
            if Path(path) != self.schema:
                return open_file(path, flags, *args, **kwargs)
            descriptor = open_file(os.devnull, flags, *args, **kwargs)
            blocking_modes.append(os.get_blocking(descriptor))
            return descriptor

        with patch.object(os, "open", side_effect=open_with_device_at_schema):
            self.assert_schema_refused()
        self.assertEqual(set(blocking_modes), {False})

    def test_full_digest_is_preserved_when_record_omits_its_optional_size(self):
        self.install_schema(b"SELECT 1;\n" * 20_000, include_size=False)
        self.assertEqual(owner.package_correlation(),
                         {"operations_commit": self.commit, "schema_sha256": self.digest.hexdigest()})

    def test_same_byte_shadow_is_refused(self):
        shadow = self.site / "shadow" / self.relative
        shadow.parent.mkdir(parents=True)
        shadow.write_bytes(self.schema.read_bytes())
        with patch.object(owner, "files", side_effect=lambda name: self.site.joinpath("shadow", *name.split("."))):
            self.assert_schema_refused()

    def test_local_directory_remains_outside_archive_contract(self):
        self.origin.write_text(json.dumps({"url": "file:///opt/cpk-bootstrap-driver-build/operations", "dir_info": {}}))
        self.assert_schema_refused()


class InitializationTargetDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        _, _, self.plan, _, _, target, _ = initialization_inputs(self)
        pg = next(node for node in self.plan["resources"]["nodes"] if node["node_id"] == self.plan["postgres_node_id"])
        mounts = [
            {"Type": "volume", "Name": item["name"], "Destination": item["target"], "RW": category == "data_volumes"}
            for category in ("data_volumes", "secret_files", "configuration_files") for item in pg[category]
        ]
        self.receipt = {
            "phase": "acquiring", "pending": None, "plan_digest": self.plan["digest"],
            "driver_image_id": self.plan["driver_image_id"], "engine_id": target["engine_id"], "labels": target["labels"],
            "resources": {"containers": {pg["node_id"]: {"id": target["postgres_container_id"]}},
                          "volumes": {mount["Name"]: {"id": mount["Name"]} for mount in mounts}},
            "observations": {"fresh_postgres_volumes": [item["name"] for item in pg["data_volumes"]],
                             "images": {pg["node_id"]: target["postgres_image_id"]}},
        }
        self.client = Mock()
        self.client.info.return_value = {"ID": target["engine_id"]}
        pg_container = self.client.containers.get.return_value
        pg_container.id = target["postgres_container_id"]
        pg_container.attrs = {"Image": target["postgres_image_id"], "Config": {"Labels": target["labels"]},
                              "State": {"Running": True}, "Mounts": mounts}
        self.client.volumes.get.side_effect = lambda name: SimpleNamespace(id=name, attrs={"Labels": target["labels"]})
        self.client.images.get.return_value.id = self.plan["driver_image_id"]

    def assert_pre_helper_refusal(self, reason):
        with self.assertRaises(bootstrap.RootBootstrapError) as caught:
            runtime.initialize_acquired_workspace(self.plan, {}, None, Path("/unused"), self.receipt, self.client, Mock())
        observed = bootstrap.bootstrap_failure(caught.exception)
        self.assertEqual((observed["stage"], observed["reason"]), ("initialization-target", reason))
        self.assertNotIn("private-path-canary", json.dumps(observed))
        self.assertNotIn("initialization_helper", self.receipt)
        self.assertIsNone(self.receipt["pending"])
        self.client.volumes.create.assert_not_called()
        self.client.containers.create.assert_not_called()

    def test_schema_refusal_precedes_helper_intent(self):
        with patch.object(owner, "distribution", side_effect=OSError("private-path-canary")) as dist:
            self.assert_pre_helper_refusal("schema-owner-unverified")
            dist.assert_called_once_with("control-plane-kit-operations")

    def test_earlier_engine_refusal_never_consults_schema(self):
        self.client.info.return_value = {"ID": "different-engine"}
        with patch.object(owner, "distribution") as dist:
            self.assert_pre_helper_refusal("initialization-target-refused")
            dist.assert_not_called()
