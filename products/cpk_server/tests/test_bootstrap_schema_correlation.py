"""Installed schema ownership and pre-effect initialization diagnostics."""
import base64
import hashlib
from importlib.metadata import FileHash, PackagePath
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_servers_cpk_server import bootstrap as api
from control_plane_kit_servers_cpk_server import bootstrap_initialization as owner
from control_plane_kit_servers_cpk_server import bootstrap_initialization_runtime as runtime


class SchemaCorrelationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.site = self.root / "site"
        self.package = self.site / "control_plane_kit_operations"
        (self.package / "postgres").mkdir(parents=True)
        self.contents = {"__init__.py": b'"""Synthetic installed package."""\n',
                         "postgres/current_schema.sql": b"-- synthetic schema\nSELECT 1;\n"}
        for relative, raw in self.contents.items():
            (self.package / relative).write_bytes(raw)
        self.commit = "b" * 40
        self.proof = self.root / "proof"
        self.proof.mkdir()
        self.cohort = {"schema": "cpk384.bootstrap-driver-cohort.v1", "operations": self.commit,
            "operations_tree": "c" * 40,
            "operations_schema_sha256": hashlib.sha256(self.contents["postgres/current_schema.sql"]).hexdigest()}
        self.objects = {"operations": {"commit": self.commit, "tree": "c" * 40,
            "prefix": "control-plane-kit-operations/src/control_plane_kit_operations"}}
        self.source_files = {"control_plane_kit_operations": {
            "distribution": "control-plane-kit-operations", "role": "operations",
            "files": {relative: hashlib.sha256(raw).hexdigest() for relative, raw in self.contents.items()}}}
        self.save_proof()
        self.dist = Mock()
        self.dist.locate_file.side_effect = lambda relative: self.site / str(relative)
        entries = []
        for relative, raw in self.contents.items():
            entry = PackagePath("control_plane_kit_operations/" + relative)
            encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
            entry.hash = FileHash("sha256=" + encoded)
            entries.append(entry)
        self.dist.files = entries
        self.origin = {"url": "file:///opt/cpk-bootstrap-driver-build/operations", "dir_info": {}}
        self.addCleanup(patch.stopall)
        patch.object(owner, "distribution", return_value=self.dist).start()
        patch.object(owner, "files", side_effect=lambda name: self.package / "postgres"
                     if name == "control_plane_kit_operations.postgres" else self.package).start()
        patch.object(owner, "_LOCAL_DRIVER_PROVENANCE", self.proof, create=True).start()

    def save_proof(self):
        for name, value in (("cohort.json", self.cohort), ("source-objects.json", self.objects),
                            ("source-files.json", self.source_files)):
            (self.proof / name).write_text(json.dumps(value))

    def correlate(self):
        self.dist.read_text.return_value = json.dumps(self.origin)
        return owner.package_correlation()

    def expected(self):
        return {"operations_commit": self.commit,
                "schema_sha256": hashlib.sha256(self.contents["postgres/current_schema.sql"]).hexdigest()}

    def test_supported_archive_origin_keeps_its_commit_and_schema(self):
        self.origin = {"url": "https://github.com/OpenJ92/control-plane-kit/archive/" + self.commit + ".zip",
                       "subdirectory": "control-plane-kit-operations"}
        self.assertEqual(self.correlate(), self.expected())

    def test_qualified_local_origin_uses_sealed_commit_and_installed_schema(self):
        self.assertEqual(self.correlate(), self.expected())

    def test_arbitrary_or_editable_local_origin_is_not_build_evidence(self):
        for origin in ({"url": "file:///tmp/unreviewed/operations", "dir_info": {}},
                       {"url": self.origin["url"], "dir_info": {"editable": True}}):
            with self.subTest(origin=origin):
                self.origin = origin
                with self.assertRaises(api.RootBootstrapError):
                    self.correlate()

    def test_missing_commit_tree_or_changed_installed_files_refuse(self):
        for fault in ("missing-proof", "commit", "tree", "schema", "module"):
            with self.subTest(fault=fault):
                if fault == "missing-proof":
                    (self.proof / "source-objects.json").unlink()
                elif fault == "commit":
                    self.objects["operations"]["commit"] = "d" * 40
                elif fault == "tree":
                    self.objects["operations"]["tree"] = "d" * 40
                else:
                    relative = "postgres/current_schema.sql" if fault == "schema" else "__init__.py"
                    (self.package / relative).write_bytes(self.contents[relative] + b"changed\n")
                if fault != "missing-proof":
                    self.save_proof()
                with self.assertRaises(api.RootBootstrapError):
                    self.correlate()
                self.objects["operations"].update(commit=self.commit, tree="c" * 40)
                for relative, raw in self.contents.items():
                    (self.package / relative).write_bytes(raw)
                self.save_proof()

    def test_schema_requires_owning_record_hash_for_both_origins(self):
        for local in (False, True):
            if not local:
                self.origin = {"url": "https://github.com/OpenJ92/control-plane-kit/archive/" + self.commit + ".zip",
                               "subdirectory": "control-plane-kit-operations"}
            else:
                self.origin = {"url": "file:///opt/cpk-bootstrap-driver-build/operations", "dir_info": {}}
            original = list(self.dist.files)
            for fault in ("missing", "unhashed", "wrong-hash"):
                with self.subTest(local=local, fault=fault):
                    schema = PackagePath("control_plane_kit_operations/postgres/current_schema.sql")
                    schema.hash = None if fault == "unhashed" else FileHash("sha256=" + "a" * 43)
                    self.dist.files = original[:1] + ([] if fault == "missing" else [schema])
                    with self.assertRaises(api.RootBootstrapError):
                        self.correlate()
            self.dist.files = original

    def test_imported_schema_cannot_be_shadowed_away_from_distribution(self):
        shadow = self.root / "shadow"
        shadow.mkdir()
        (shadow / "current_schema.sql").write_bytes(self.contents["postgres/current_schema.sql"])
        with patch.object(owner, "files", return_value=shadow), self.assertRaises(api.RootBootstrapError):
            self.correlate()


class InitializationTargetDiagnosticTests(unittest.TestCase):
    def test_schema_refusal_has_its_own_bounded_category_before_helper_intent(self):
        client, sdk = Mock(), Mock()
        plan = {"postgres_node_id": "pg"}
        receipt = {"phase": "acquiring", "pending": None, "resources": {"containers": {"pg": {"id": "x"}}}}
        with patch.object(runtime, "_target", side_effect=api.RootBootstrapError(
                "bootstrap installed schema owner could not be verified")):
            with self.assertRaises(api.RootBootstrapError) as caught:
                runtime.initialize_acquired_workspace(plan, {}, None, Path("/unused"), receipt, client, sdk)
        observed = api.bootstrap_failure(caught.exception)
        self.assertEqual((observed["stage"], observed["reason"]),
                         ("initialization-target", "schema-owner-unverified"))
        self.assertNotIn("initialization_helper", receipt)
        client.containers.create.assert_not_called()
        client.volumes.create.assert_not_called()

    def test_earlier_target_refusal_does_not_blame_schema_owner(self):
        client, sdk = Mock(), Mock()
        client.info.return_value = {"ID": "different-daemon"}
        plan = {"postgres_node_id": "pg", "digest": "plan", "driver_image_id": "driver"}
        receipt = {"phase": "acquiring", "pending": None, "plan_digest": "plan", "driver_image_id": "driver",
                   "engine_id": "approved-daemon", "resources": {"containers": {"pg": {"id": "x"}}}}
        with patch.object(runtime, "package_correlation") as correlation:
            with self.assertRaises(api.RootBootstrapError) as caught:
                runtime.initialize_acquired_workspace(plan, {}, None, Path("/unused"), receipt, client, sdk)
        observed = api.bootstrap_failure(caught.exception)
        self.assertEqual((observed["stage"], observed["reason"]),
                         ("initialization-target", "initialization-target-refused"))
        correlation.assert_not_called()
        self.assertNotIn("initialization_helper", receipt)
        client.containers.create.assert_not_called()
        client.volumes.create.assert_not_called()
