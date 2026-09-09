"""Bootstrap-owned Docker Hub spelling equivalence; no runtime or registry IO."""

import unittest

from control_plane_kit_servers_cpk_server import bootstrap


class RootImageReferenceTests(unittest.TestCase):
    def test_official_library_spellings_preserve_repository_and_exact_digest(self):
        digest = "sha256:" + "a" * 64
        expected = "docker.io/library/postgres@" + digest
        for spelling in ("docker.io/library/postgres", "postgres", "library/postgres", "docker.io/postgres"):
            with self.subTest(spelling=spelling):
                self.assertTrue(bootstrap.matches_image_reference(expected, (spelling + "@" + digest,)))

    def test_no_digest_only_foreign_repository_or_non_hub_alias_acceptance(self):
        digest = "sha256:" + "a" * 64
        expected = "docker.io/library/postgres@" + digest
        for observed in (
            (), (digest,), ("postgres:latest",),
            ("postgres@sha256:" + "b" * 64,),
            ("redis@" + digest,), ("library/redis@" + digest,),
            ("docker.io/foreign/postgres@" + digest,),
            ("foreign.example/library/postgres@" + digest,),
            ("ghcr.io/library/postgres@" + digest,),
            ("postgres@" + digest + "-suffix",),
        ):
            with self.subTest(observed=observed):
                self.assertFalse(bootstrap.matches_image_reference(expected, observed))
        for product in ("cpk-server", "secrets-server"):
            canonical = "ghcr.io/openj92/control-plane-kit-servers/" + product + "@" + digest
            self.assertTrue(bootstrap.matches_image_reference(canonical, (canonical,)))
            for alias in (product + "@" + digest, "openj92/control-plane-kit-servers/" + product + "@" + digest):
                self.assertFalse(bootstrap.matches_image_reference(canonical, (alias,)))


if __name__ == "__main__":
    unittest.main()
