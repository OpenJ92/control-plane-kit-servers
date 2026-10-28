"""Bounded correspondence/account projection; no image acquisition or unpack."""
import copy
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess


SOURCE = "a" * 40


class RootAccountProjectionTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("root_account_projection",
            Path(__file__).resolve().parents[3] / "scripts/root_account_projection.py")
        self.owner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.owner)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def encoded(self, value):
        return json.dumps(value, sort_keys=True).encode()

    def write_blob(self, raw, media):
        digest = self.owner.sha(raw)
        (self.root / "layout" / "blobs" / "sha256" / digest[7:]).write_bytes(raw)
        return {"mediaType": media, "digest": digest, "size": len(raw)}

    def fixture(self, *, schema2=False, change=None):
        owner = self.owner
        (self.root / "layout" / "blobs" / "sha256").mkdir(parents=True, exist_ok=True)
        config = {"os": "linux", "architecture": "amd64", "config": {"User": "10001",
            "Labels": {"org.opencontainers.image.revision": SOURCE}},
            "rootfs": {"type": "layers", "diff_ids": [owner.sha(b"uncompressed-layer")]}}
        original = {"schemaVersion": 2, "mediaType": owner.OCI + "manifest.v1+json"}
        original["config"] = self.write_blob(self.encoded(config), owner.OCI + "config.v1+json")
        # Hash correspondence alone does not establish that these synthetic bytes
        # are a layer or that umoci ran. Full unpack is deliberately separate.
        original["layers"] = [self.write_blob(b"synthetic-layer-blob", owner.OCI + "layer.v1.tar+gzip")]
        if schema2:
            original["mediaType"] = owner.DOCKER + "manifest.v2+json"
            original["config"]["mediaType"] = "application/vnd.docker.container.image.v1+json"
            original["layers"][0]["mediaType"] = "application/vnd.docker.image.rootfs.diff.tar.gzip"
        normalized = copy.deepcopy(original)
        normalized["mediaType"] = owner.OCI + "manifest.v1+json"
        normalized["config"]["mediaType"] = owner.OCI + "config.v1+json"
        normalized["layers"][0]["mediaType"] = owner.OCI + "layer.v1.tar+gzip"
        if change is not None:
            change(original, normalized, config)
        normalized_entry = self.write_blob(self.encoded(normalized), owner.OCI + "manifest.v1+json")
        normalized_entry["annotations"] = {"org.opencontainers.image.ref.name": "inspected"}
        (self.root / "layout" / "index.json").write_bytes(self.encoded(
            {"schemaVersion": 2, "manifests": [normalized_entry]}))
        (self.root / "layout" / "oci-layout").write_bytes(self.encoded({"imageLayoutVersion": "1.0.0"}))
        platform = self.encoded(original)
        original_entry = {"mediaType": original["mediaType"], "digest": owner.sha(platform), "size": len(platform),
            "platform": {"os": "linux", "architecture": "amd64"}}
        index = self.encoded({"schemaVersion": 2, "mediaType": owner.OCI + "index.v1+json",
            "manifests": [original_entry]})
        (self.root / "original.json").write_bytes(index)
        (self.root / "platform.json").write_bytes(platform)
        return "ghcr.io/openj92/control-plane-kit-servers/cpk-server@" + owner.sha(index)

    def verify(self, reference):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            return self.owner.verify_layout(fd, reference, SOURCE)
        finally:
            os.close(fd)

    def test_original_and_normalized_identities_preserve_actual_content_correspondence(self):
        for schema2 in (False, True):
            with self.subTest(schema2=schema2):
                reference = self.fixture(schema2=schema2)
                result = self.verify(reference)
                self.assertEqual(result["image_reference"], reference)
                self.assertEqual(result["platform"], "linux/amd64")
                self.assertEqual(result["layer_count"], 1)
                self.assertEqual(result["platform_manifest_digest"] == result["normalized_manifest_digest"], not schema2)
                self.assertNotIn("uid", result)  # Correspondence is not an account seal.

    def test_pre_copy_selection_binds_the_exact_original_and_unique_platform(self):
        reference = self.fixture()
        raw = (self.root / "original.json").read_bytes()
        selected = self.owner.manifest_selection(raw, reference)
        self.assertEqual(selected["digest"], self.owner.sha((self.root / "platform.json").read_bytes()))
        single = (self.root / "platform.json").read_bytes()
        self.assertEqual(self.owner.manifest_selection(single,
            reference.split("@")[0] + "@" + self.owner.sha(single))["digest"], self.owner.sha(single))
        original = json.loads(raw)
        original["manifests"] *= 2
        ambiguous = self.encoded(original)
        with self.assertRaises(self.owner.AccountInspectionError):
            self.owner.manifest_selection(ambiguous, reference.split("@")[0] + "@" + self.owner.sha(ambiguous))
        with self.assertRaises(self.owner.AccountInspectionError):
            self.owner.manifest_selection(raw, reference[:-1] + ("0" if reference[-1] != "0" else "1"))

    def test_pre_copy_admission_refuses_foreign_and_oversized_sources_without_layout(self):
        for change in (None,
                lambda original, normalized, config: original["layers"][0].update(urls=["https://example.invalid/foreign"]),
                lambda original, normalized, config: original["layers"][0].update(size=self.owner.COMPRESSED_LIMIT + 1)):
            reference = self.fixture(change=change)
            # Admission reads only original/platform metadata, before any OCI copy.
            layout = self.root / "layout"
            held = self.root / "not-acquired"
            layout.rename(held)
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                if change is None:
                    raw, config, layers = self.owner.admitted_manifest(fd, reference)
                    self.assertEqual(raw, (self.root / "platform.json").read_bytes())
                    self.assertEqual(len(layers), 1)
                    self.assertTrue(self.owner.digest(config["digest"]))
                else:
                    with self.assertRaises(self.owner.AccountInspectionError):
                        self.owner.admitted_manifest(fd, reference)
            finally:
                os.close(fd)
                held.rename(layout)

    def test_ambiguous_index_duplicate_keys_and_wrong_reference_refuse(self):
        reference = self.fixture()
        with self.assertRaises(self.owner.AccountInspectionError):
            self.verify(reference[:-1] + ("0" if reference[-1] != "0" else "1"))
        original = json.loads((self.root / "original.json").read_bytes())
        original["manifests"] *= 2
        raw = self.encoded(original)
        (self.root / "original.json").write_bytes(raw)
        with self.assertRaises(self.owner.AccountInspectionError):
            self.verify(reference.split("@")[0] + "@" + self.owner.sha(raw))
        with self.assertRaises(self.owner.AccountInspectionError):
            self.owner.document(b'{"size":1,"size":2}')

    def test_config_platform_user_and_diff_count_are_not_inferred_from_index(self):
        for key, value in (("os", "windows"), ("architecture", "arm64"),
                ("config", {"User": "0"}), ("rootfs", {"type": "layers", "diff_ids": []})):
            def change(original, normalized, config):
                config[key] = value
                selected = self.write_blob(self.encoded(config), self.owner.OCI + "config.v1+json")
                original["config"] = normalized["config"] = selected
            reference = self.fixture(change=change)
            with self.subTest(key=key), self.assertRaises(self.owner.AccountInspectionError):
                self.verify(reference)

    def test_foreign_layers_normalization_drift_and_corrupted_blob_refuse(self):
        changes = (
            lambda original, normalized, config: original["layers"][0].update(urls=["https://example.invalid/private"]),
            lambda original, normalized, config: normalized["layers"][0].update(size=True),
            lambda original, normalized, config: normalized["layers"].append(normalized["layers"][0]),
            lambda original, normalized, config: normalized["config"].update(digest="sha256:" + "c" * 64),
        )
        for change in changes:
            reference = self.fixture(change=change)
            with self.assertRaises(self.owner.AccountInspectionError):
                self.verify(reference)
        reference = self.fixture()
        layer = json.loads((self.root / "platform.json").read_bytes())["layers"][0]
        (self.root / "layout" / "blobs" / "sha256" / layer["digest"][7:]).write_bytes(b"x" * layer["size"])
        with self.assertRaises(self.owner.AccountInspectionError):
            self.verify(reference)

    def accounts(self, *, passwd=None, group=None):
        etc = self.root / "bundle" / "rootfs" / "etc"
        etc.mkdir(parents=True, exist_ok=True)
        (etc / "passwd").write_bytes(passwd or b"root:x:0:0:root:/root:/bin/sh\ncpk:x:10001:10001::/home/cpk:/bin/sh\n")
        (etc / "group").write_bytes(group or b"root:x:0:\ncpk:x:10001:\nusers:x:100:cpk\nextra:x:101:other,cpk\n")
        return etc

    def project(self):
        fd = os.open(self.root / "bundle", os.O_RDONLY | os.O_DIRECTORY)
        try:
            return self.owner.project_accounts(fd)
        finally:
            os.close(fd)

    def test_complete_final_membership_is_derived_from_file_content(self):
        etc = self.accounts()
        result = self.project()
        self.assertEqual((result["uid"], result["primary_gid"], result["supplementary_gids"]), (10001, 10001, [100, 101]))
        self.assertEqual(result["passwd_sha256"], hashlib.sha256((etc / "passwd").read_bytes()).hexdigest())
        self.assertNotIn("root:x", json.dumps(result))

    def test_account_ambiguity_and_oversized_content_refuse(self):
        for passwd, group in ((b"cpk:x:10001:10001::/:/bin/sh\nother:x:10001:10001::/:/bin/sh\n", None),
                (None, b"cpk:x:10001:\nalias:x:10001:cpk\n"), (b"x" * 65537, None)):
            self.accounts(passwd=passwd, group=group)
            with self.assertRaises(self.owner.AccountInspectionError):
                self.project()

    def test_account_files_and_ancestors_do_not_follow_links(self):
        etc = self.accounts()
        (etc / "passwd").rename(etc / "saved")
        (etc / "passwd").symlink_to("saved")
        with self.assertRaises(OSError):
            self.project()
        (etc / "passwd").unlink()
        os.link(etc / "saved", etc / "passwd")
        with self.assertRaises(self.owner.AccountInspectionError):
            self.project()
        (etc / "passwd").unlink()
        (etc / "saved").rename(etc / "passwd")
        etc.rename(etc.with_name("saved-etc"))
        etc.symlink_to("saved-etc", target_is_directory=True)
        with self.assertRaises(OSError):
            self.project()

    def test_offline_cli_reports_only_the_reached_failure_boundary(self):
        # These are process/filesystem boundary doubles, not an unpacker or a
        # successful account seal. Every case fails before any result is emitted.
        cases = (
            (40, "input-setup", "open", OSError("private-path-canary")),
            (41, "layout-validation", "verify_layout", ValueError("private-config-canary")),
            (42, "tool-validation", "read_file", OSError("private-tool-canary")),
            (43, "unpack-launch", "run", OSError("private-command-canary")),
            (44, "unpack-timeout", "run", subprocess.TimeoutExpired("private-command-canary", 180)),
            (45, "unpack-nonzero", "nonzero", None),
            (46, "account-projection", "project_accounts", ValueError("private-account-canary")),
            (47, "result-serialization", "dumps", ValueError("private-result-canary")),
        )
        for code, label, failing, error in cases:
            with self.subTest(label=label), ExitStack() as stack:
                targets = {
                    "open": (self.owner.os, "open", 10),
                    "verify_layout": (self.owner, "verify_layout", {}),
                    "read_file": (self.owner, "read_file", self.owner.UMOCI_SHA256),
                    "run": (self.owner.subprocess, "run", subprocess.CompletedProcess([], 0)),
                    "project_accounts": (self.owner, "project_accounts", {}),
                    "dumps": (self.owner.json, "dumps", "{}"),
                }
                mocks = {}
                for name, (target, attribute, value) in targets.items():
                    mocks[name] = stack.enter_context(patch.object(target, attribute, return_value=value))
                stack.enter_context(patch.object(self.owner.os, "close"))
                stack.enter_context(patch.object(self.owner.tempfile, "mkdtemp", return_value="/inspection/synthetic"))
                if failing == "nonzero":
                    mocks["run"].return_value = subprocess.CompletedProcess([], 17)
                else:
                    mocks[failing].side_effect = error
                output, errors = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(errors):
                    result = self.owner.main(["ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:" + "b" * 64, SOURCE])
                self.assertEqual(result, code)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(errors.getvalue(), "root image account inspection refused\n"
                    + "cpk-root-account-stage-v1:" + label + "\n")
                if code < 43:
                    mocks["run"].assert_not_called()
                if code < 46:
                    mocks["project_accounts"].assert_not_called()
