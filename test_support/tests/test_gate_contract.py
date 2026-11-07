from __future__ import annotations

import os
from pathlib import Path
import unittest


class PackageGateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(
            os.environ.get("CPK_PACKAGE_ROOT", Path(__file__).resolve().parents[2])
        )
        cls.gate = cls.root / "test.sh"
        cls.source = cls.gate.read_text(encoding="utf-8")

    def test_gate_is_executable_and_anchors_itself_to_repository_root(self) -> None:
        self.assertTrue(os.access(self.gate, os.X_OK))
        self.assertIn('ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"', self.source)
        self.assertIn('cd "$ROOT"', self.source)

    def test_generated_coordinates_are_checked_before_build(self) -> None:
        coordinate_check = self.source.index("scripts/apply_coordinates.py --check")
        image_build = self.source.index("docker build -f Dockerfile.test")
        self.assertLess(coordinate_check, image_build)

    def test_integrity_scan_covers_root_and_product_source_and_tests(self) -> None:
        for expected in (
            "--source-root src",
            "--source-root products",
            "--test-root tests",
            "--test-root products",
        ):
            self.assertIn(expected, self.source)

    def test_http_sample_focus_preserves_checks_and_exits_before_full_gate(self) -> None:
        self.assertIn('--http-sample-relay)', self.source)
        focus = self.source.index('if [ "$HTTP_SAMPLE_RELAY_ONLY" != 0 ]; then')
        self.assertLess(self.source.index('scripts/apply_coordinates.py --check'), focus)
        self.assertLess(self.source.index('--test-root products'), focus)
        end = self.source.index('docker run --rm "$IMAGE"\n', focus)
        branch = self.source[focus:end]
        self.assertIn('--network none', branch)
        self.assertNotIn('docker.sock', branch)
        self.assertIn('test_http_sample_relay.py', branch)
        self.assertIn('test_health_relay.py', branch)
        self.assertIn('exit 0', branch)

    def test_combined_sample_fixture_is_exact_read_only_source(self) -> None:
        fixture = (self.root / 'scripts/http_sample_combined.sh').read_text()
        self.assertIn('--http-sample-combined)', self.source)
        self.assertIn('merge-base --is-ancestor', fixture)
        self.assertIn('git -C "$sender_repository" archive', fixture)
        self.assertIn('d5765cdffb4c2a02d4be9b81b401e96c17e4624b', fixture)
        self.assertIn('--network none --read-only', fixture)
        self.assertIn('target=/reviewed-sender/src,readonly', fixture)
        self.assertNotIn('docker.sock', fixture)

    def test_image_smoke_cannot_inherit_a_build_disabling_option(self) -> None:
        self.assertIn(
            "CPK_SERVER_BUILD_IMAGE=1 sh scripts/cpk_server_image_smoke.sh",
            self.source,
        )

    def test_residue_audit_is_the_last_authoritative_phase(self) -> None:
        self.assertLess(
            self.source.index("scripts/cpk_server_image_smoke.sh"),
            self.source.index("scripts/docker_residue_audit.sh"),
        )
        self.assertTrue(self.source.rstrip().endswith("sh scripts/docker_residue_audit.sh"))


if __name__ == "__main__":
    unittest.main()
