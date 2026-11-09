"""OCI transport integrity at the packaging boundary, without a Docker daemon."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import subprocess
import sys
import grandparent_oci

from grandparent_oci import validate_export


class LocalBaseTests(unittest.TestCase):
    def fixture(self, directory, *, corrupt=False, platform="amd64"):
        blobs = {}

        def blob(content):
            raw = content if type(content) is bytes else json.dumps(content).encode()
            digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            blobs["blobs/sha256/" + digest.removeprefix("sha256:")] = raw
            return {"digest": digest, "size": len(raw)}

        layer = blob(b"synthetic-compressed-layer")
        config = blob({"os": "linux", "architecture": platform,
            "config": {"User": "10001", "Cmd": ["python", "-m", "control_plane_kit_servers_cpk_server.server"]},
            "rootfs": {"type": "layers", "diff_ids": ["sha256:" + "a" * 64]}})
        manifest = blob({"schemaVersion": 2, "config": config, "layers": [layer]})
        manifest["platform"] = {"architecture": platform, "os": "linux"}
        base = blob({"schemaVersion": 2, "manifests": [manifest]})
        if corrupt:
            blobs["blobs/sha256/" + layer["digest"].removeprefix("sha256:")] = b"substituted-layer"
        blobs.update({"oci-layout": b'{"imageLayoutVersion":"1.0.0"}',
                      "index.json": json.dumps({"schemaVersion": 2, "manifests": [base]}).encode()})
        archive = directory / "base.tar"
        with tarfile.open(archive, "w") as output:
            for name in ("blobs/", "blobs/sha256/"):
                member = tarfile.TarInfo(name)
                member.type = tarfile.DIRTYPE
                output.addfile(member)
            for name, raw in blobs.items():
                member = tarfile.TarInfo(name)
                member.size = len(raw)
                output.addfile(member, io.BytesIO(raw))
        layout = directory / "layout"
        layout.mkdir()
        return archive, layout, base["digest"]

    def test_exact_local_layout_preserves_base_and_content_identity(self):
        with tempfile.TemporaryDirectory() as name:
            archive, layout, digest = self.fixture(Path(name))
            result = validate_export(archive, layout, digest)
            self.assertEqual(result["base_digest"], digest)
            self.assertEqual(result["architecture"], "amd64")
            self.assertTrue(result["all_blob_digests_verified"])

    def test_substituted_blob_and_wrong_platform_refuse(self):
        for options in ({"corrupt": True}, {"platform": "arm64"}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as name:
                archive, layout, digest = self.fixture(Path(name), **options)
                with self.assertRaises(AssertionError):
                    validate_export(archive, layout, digest)

    def test_wrong_selected_digest_is_not_normalized_or_reconstructed(self):
        with tempfile.TemporaryDirectory() as name:
            archive, layout, _ = self.fixture(Path(name))
            with self.assertRaises(AssertionError):
                validate_export(archive, layout, "sha256:" + "b" * 64)

    def test_optimized_interpreter_refuses_before_layout_writes(self):
        with tempfile.TemporaryDirectory() as name:
            archive, layout, _ = self.fixture(Path(name))
            result = subprocess.run([sys.executable, "-O", grandparent_oci.__file__, str(archive), str(layout)],
                                    capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(layout.iterdir()), [])
