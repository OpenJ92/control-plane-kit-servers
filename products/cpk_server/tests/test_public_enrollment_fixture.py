"""Closed fresh-fixture admission, before Docker or private legacy setup."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from products.cpk_server.tests.live_numeric_bootstrap import _enrollment_inputs
from scripts.cpk_server_source_live_report import SourceLiveInvariantError


class PublicEnrollmentFixtureAdmissionTests(unittest.TestCase):
    def test_exact_nonsecret_launch_coordinates_are_required(self):
        values = {"CPK_G_RUN": "cpk-enrollment-fixture", "CPK_G_ENGINE": "engine-identity",
            "CPK_G_NETWORK": "a" * 64, **{"CPK_G_" + role + "_IMAGE": "sha256:" + "b" * 64
                for role in ("CONTROLLER", "CPK", "SECRETS", "POSTGRES")}}
        admitted = _enrollment_inputs(values)
        self.assertEqual(admitted["network"], values["CPK_G_NETWORK"])
        for name in values:
            for invalid in ("", "Bearer private-material\n", "../not-valid"):
                with self.subTest(field=name, invalid=invalid):
                    with self.assertRaises(SourceLiveInvariantError) as failure:
                        _enrollment_inputs({**values, name: invalid})
                    self.assertEqual(str(failure.exception), "enrollment-launch-input-invalid")

    def test_missing_g_images_refuses_before_docker_and_legacy_inputs(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            marker = temporary / "docker-was-called"
            docker = temporary / "docker"
            docker.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
            docker.chmod(0o700)
            environment = {**os.environ, "PATH": str(temporary) + ":" + os.environ["PATH"],
                "CPK_SECRET_PROVIDER_SOURCE_LIVE_SCENARIO": "public-workspace-enrollment",
                "CPK_SECRETS_REPO": str(temporary / "nonexistent-legacy-repository")}
            for name in ("CPK_SERVERS_TEST_IMAGE", "CPK_SECRET_PROVIDER_SERVER_IMAGE",
                         "CPK_SECRETS_TEST_IMAGE", "CPK_LIVE_POSTGRES_IMAGE"):
                environment.pop(name, None)
            result = subprocess.run(["sh", str(root / "scripts/cpk_server_secret_provider_source_live_smoke.sh")],
                env=environment, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr.strip(), "public enrollment requires explicit source images")
            self.assertFalse(marker.exists())
