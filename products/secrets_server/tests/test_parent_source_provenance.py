"""Synthetic public-code seals; no actual provider image or Secrets source is claimed."""
import base64
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import image_check


class ParentSourceProvenanceTests(unittest.TestCase):
    def fixture(self, root):
        source, public = root / "source", root / "public"
        module = source / image_check.PARENT_PREFIX
        module.mkdir(parents=True)
        lines = []
        for name, raw in (("__init__.py", b"# public unit source\n"), ("py.typed", b"")):
            (module / name).write_bytes(raw)
            digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            lines.append("100644 blob " + digest + "\t" + image_check.PARENT_PREFIX + name)
        (source / ".cpk-secrets.git-tree").write_text("\n".join(lines) + "\n")
        # Explicit fake tuple: these unit bytes do not impersonate source57.
        (source / ".cpk-source-objects.json").write_text(json.dumps({
            "commit":"e" * 40, "tree":"f" * 40, "prefix":image_check.PARENT_PREFIX}))
        return source, public, module

    def selected_fixture(self):
        return patch.multiple(image_check, PARENT_SECRETS="e" * 40, PARENT_TREE="f" * 40)

    def test_exact_export_is_sealed_once_with_readable_public_manifest(self):
        with TemporaryDirectory() as directory, self.selected_fixture():
            source, public, module = self.fixture(Path(directory))
            result = image_check.seal_parent(source, public)
            self.assertEqual(result["git_commit"], "e" * 40)
            self.assertEqual(result["source_files_sealed"], 2)
            self.assertEqual(json.loads((public / "source-files.json").read_text()), image_check.source_files(module))
            self.assertEqual((public / "source-files.json").stat().st_mode & 0o777, 0o444)
            with self.assertRaises(FileExistsError):
                image_check.seal_parent(source, public)

    def test_changed_blob_wrong_tuple_extra_source_and_symlink_refuse(self):
        for fault in ("blob", "tuple", "extra", "symlink"):
            with self.subTest(fault=fault), TemporaryDirectory() as directory, self.selected_fixture():
                source, public, module = self.fixture(Path(directory))
                if fault == "blob":
                    (module / "__init__.py").write_bytes(b"modified public code")
                elif fault == "tuple":
                    (source / ".cpk-source-objects.json").write_text("{}")
                elif fault == "extra":
                    (module / "extra.py").write_text("# extra")
                else:
                    (module / "extra.py").symlink_to("__init__.py")
                with self.assertRaises(ValueError):
                    image_check.seal_parent(source, public)
                self.assertFalse(public.exists())

    def test_installed_source_and_record_must_both_match_the_seal(self):
        with TemporaryDirectory() as directory, self.selected_fixture():
            root = Path(directory)
            source, public, module = self.fixture(root)
            image_check.seal_parent(source, public)
            installed = root / "site" / "control_plane_kit_secrets"
            shutil.copytree(module, installed)
            items = []
            for name in ("__init__.py", "py.typed"):
                digest = base64.urlsafe_b64encode(hashlib.sha256((installed / name).read_bytes()).digest()).decode().rstrip("=")
                items.append(SimpleNamespace(hash=SimpleNamespace(mode="sha256", value=digest), name=name))
            def locate(value):
                return installed if value == "control_plane_kit_secrets" else installed / value.name
            dist = SimpleNamespace(locate_file=locate, files=items)
            with patch.object(image_check.metadata, "distribution", return_value=dist), \
                    patch.object(image_check, "import_module", return_value=SimpleNamespace(__file__=str(installed / "__init__.py"))):
                result = image_check.parent_source_provenance(public)
                self.assertEqual(result["source_files_verified"], 2)
                self.assertEqual(result["record_files_verified"], 2)
                items[0].hash.value = "invalid-record"
                with self.assertRaisesRegex(ValueError, "parent distribution record differs"):
                    image_check.parent_source_provenance(public)
                (installed / "__init__.py").write_text("# replaced")
                with self.assertRaisesRegex(ValueError, "installed parent source differs"):
                    image_check.parent_source_provenance(public)
