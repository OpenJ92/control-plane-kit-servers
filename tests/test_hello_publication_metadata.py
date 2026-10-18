"""Pure provider-response laws; these do not simulate a successful publication."""
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hello_publication_metadata.py"
DESTINATION = SCRIPT.with_name("hello_publication_destination.sh")
validate = runpy.run_path(str(SCRIPT))["validate"]
SOURCE = "a" * 40
TAG = "hello-271-" + SOURCE
REFERENCE = "ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:" + "b" * 64


def package():
    return {"id": 13951244, "name": "control-plane-kit-servers/hello-server",
            "package_type": "container", "visibility": "private",
            "repository": {"full_name": "OpenJ92/control-plane-kit-servers"}}


def version(identity=1, tags=None, digest=None):
    return {"id": identity, "name": digest or REFERENCE.split("@")[1],
            "metadata": {"container": {"tags": [TAG] if tags is None else tags}}}


class HelloPublicationMetadataTests(unittest.TestCase):
    def test_pure_destination_accepts_only_the_exact_source_bound_hello_target(self):
        result = subprocess.run(["sh", str(DESTINATION), "openj92", "control-plane-kit-servers", TAG, SOURCE],
            capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
            "ghcr.io/openj92/control-plane-kit-servers/hello-server:" + TAG + "\n")

    def test_pure_destination_refuses_owner_package_tag_and_source_overrides(self):
        valid = ["openj92", "control-plane-kit-servers", TAG, SOURCE]
        for index, value in ((0, "another-owner"), (0, "OpenJ92"),
                (1, "another-package"), (1, "control-plane-kit-servers/../elsewhere"),
                (2, "latest"), (2, TAG + "\n"), (2, "$(unsafe)"),
                (3, "a" * 7), (3, "a" * 41), (3, "A" * 40), (3, "a" * 39 + "g")):
            arguments = valid.copy()
            arguments[index] = value
            with self.subTest(arguments=arguments):
                result = subprocess.run(["sh", str(DESTINATION), *arguments],
                    capture_output=True, text=True, timeout=5, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_unused_tag_requires_the_exact_private_package_and_all_pages(self):
        evidence = validate(package(), [[version(tags=["historical"])], []], SOURCE)
        self.assertEqual(evidence, {"package_id": 13951244,
            "visibility": "private", "unused_tag": TAG})
        with self.assertRaises(ValueError):
            validate(package(), [[version(tags=["historical"])], [version(2)]], SOURCE)

    def test_public_absent_wrong_identity_and_wrong_repository_refuse(self):
        cases = [None, {}, False]
        for field, value in (("id", 16002678), ("id", True), ("visibility", "public"),
                ("visibility", "internal"), ("name", "control-plane-kit-servers/counter-witness"),
                ("package_type", "npm"), ("repository", None),
                ("repository", {"full_name": "another/repository"})):
            invalid = package()
            invalid[field] = value
            cases.append(invalid)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate(value, [[]], SOURCE)

    def test_missing_malformed_duplicate_and_incomplete_page_shapes_refuse(self):
        bad = version(tags=[TAG, TAG])
        for pages in (None, [], {}, [None], [[None]], [[{}]],
                [[version()], [version()]], [[bad]],
                [[{"id": 1, "name": "digest", "metadata": {"container": {"tags": None}}}]]):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                validate(package(), pages, SOURCE)

    def test_post_push_requires_one_exact_tag_digest_association(self):
        result = validate(package(), [[version(tags=["old"])], [version(2)]], SOURCE, REFERENCE)
        self.assertEqual(result["version_id"], 2)
        self.assertEqual(result["reference"], REFERENCE)
        for pages in ([[]], [[version(digest="sha256:" + "c" * 64)]],
                [[version()], [version(2)]], [[version(tags=["some-other-tag"])]]):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                validate(package(), pages, SOURCE, REFERENCE)
        for reference in (REFERENCE.replace("hello-server", "counter-witness"),
                REFERENCE[:-1], REFERENCE.upper(), REFERENCE + "\n"):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                validate(package(), [[version()]], SOURCE, reference)

    def test_source_is_an_exact_full_commit(self):
        for source in ("", "a" * 7, "a" * 41, "A" * 40, SOURCE + "\n", "$(unsafe)"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate(package(), [[]], source)

    def test_command_refuses_missing_or_corrupt_evidence_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for content in (None, "{broken", json.dumps(package())):
                if content is not None:
                    (root / "package.json").write_text(content)
                result = subprocess.run([sys.executable, str(SCRIPT), directory, SOURCE, "before-push"],
                    capture_output=True, text=True, check=False, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)
            (root / "versions.json").write_text(json.dumps([[]]))
            result = subprocess.run([sys.executable, str(SCRIPT), directory, SOURCE, "before-push"],
                capture_output=True, text=True, check=False, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["unused_tag"], TAG)
