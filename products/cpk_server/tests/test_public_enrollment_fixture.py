"""Closed fresh-fixture admission, before Docker or private legacy setup."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
import json
from unittest.mock import Mock, patch

from products.cpk_server.tests.live_numeric_bootstrap import (
    _enrollment_inputs, _enrollment_management_environment, _finish_enrollment, _enrollment_ready,
)
from scripts.cpk_server_source_live_report import SourceLiveInvariantError, SourceLiveRunFailed


class PublicEnrollmentFixtureAdmissionTests(unittest.TestCase):
    def test_transport_unavailable_consumes_bounded_readiness_attempts(self):
        import httpx
        container = Mock(status="running")
        with patch("httpx.Client") as client, patch(
                "products.cpk_server.tests.live_numeric_bootstrap.time.sleep") as pause:
            get = client.return_value.__enter__.return_value.get
            get.side_effect = httpx.ConnectError("private transport detail")
            with self.assertRaises(SourceLiveInvariantError) as failure:
                _enrollment_ready(container, "http://127.0.0.1:8080/health/live")
        self.assertEqual(str(failure.exception), "enrollment-readiness-unavailable")
        self.assertEqual(get.call_count, 40)
        self.assertEqual(pause.call_count, 40)

    def test_readiness_can_succeed_after_unavailable_observation(self):
        import httpx
        container = Mock(status="running")
        with patch("httpx.Client") as client, patch(
                "products.cpk_server.tests.live_numeric_bootstrap.time.sleep") as pause:
            get = client.return_value.__enter__.return_value.get
            get.side_effect = [httpx.ConnectError("private transport detail"), Mock(status_code=200)]
            _enrollment_ready(container, "http://127.0.0.1:8080/health/live")
        self.assertEqual(get.call_count, 2)
        pause.assert_called_once_with(0.25)

    def test_management_environment_accepts_dynamic_owner_configuration(self):
        from managed_native_material import NativeMaterial
        from test_secret_provider_bootstrap import _provider_environment
        from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
        from control_plane_kit_servers_cpk_server.server import CpkServerBootstrapConfiguration
        world = NativeMaterial()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "managed.json"
            policy_path = Path(directory) / "workspace.json"
            identity = PrincipalIdentity("issuer-g", "administrator-g", PrincipalKind.OPERATOR).descriptor()
            policy_path.write_text(json.dumps({"schema": "cpk-server.workspace-authority.v1",
                "installation_id": "installation-g", "administrators": [identity],
                "known_identities": [identity], "capabilities": ["g-local-docker"]}))
            path.write_text(json.dumps({"schema": "cpk-server.managed-health.v2",
                "docker": {"socket_path": "/var/run/docker.sock", "request_timeout": 5.0},
                "capability_ids": ["g-local-docker"],
                "gateway_documents": [world.authored.documents["gateway"].content.decode()],
                "native_product_document": world.document.content.decode()}))
            config = CpkServerBootstrapConfiguration.from_environment({
                **_provider_environment(Path(directory) / "unread.token"),
                "CPK_WORKSPACE_AUTHORITY": "dynamic-v1",
                "CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE": str(policy_path),
                **_enrollment_management_environment(path)})
            self.assertIsNone(config.managed_health_process.provider_clients)

    def test_uncertain_or_failed_scenario_keeps_cohort_and_records(self):
        for primary, uncertain in ((SourceLiveRunFailed("public-outcome-uncertain"), False),
                                   (SourceLiveInvariantError("scenario-incomplete"), True)):
            dispose, close, marker = Mock(), Mock(), Mock()
            _finish_enrollment(primary, uncertain, dispose, close, marker)
            dispose.assert_not_called()
            marker.assert_not_called()
            close.assert_called_once_with()
        dispose, close, marker = Mock(), Mock(), Mock()
        with self.assertRaises(SourceLiveRunFailed):
            _finish_enrollment(None, True, dispose, close, marker)
        dispose.assert_not_called()
        marker.assert_not_called()

    def test_primary_identity_survives_close_failure_without_private_exception(self):
        dispose, marker = Mock(), Mock()
        with self.assertRaises(SourceLiveRunFailed) as failure:
            _finish_enrollment(SourceLiveRunFailed("public-outcome-uncertain", "public-cleanup-uncertain"),
                False, dispose, Mock(side_effect=OSError("private-material")), marker)
        self.assertEqual(failure.exception.primary_code, "public-outcome-uncertain")
        self.assertEqual(failure.exception.cleanup_code, "enrollment-cleanup-failed")
        self.assertNotIn("private-material", str(failure.exception))
        dispose.assert_not_called()
        marker.assert_not_called()

    def test_success_disposes_before_absence_and_marker_failure_is_bounded(self):
        calls = []
        _finish_enrollment(None, False, lambda: calls.append("dispose"),
            lambda: calls.append("close"), lambda: calls.append("absent"))
        self.assertEqual(calls, ["dispose", "close", "absent"])
        for failing_phase in ("dispose", "close", "marker"):
            steps = {name: Mock(side_effect=OSError("private-material") if name == failing_phase else None)
                     for name in ("dispose", "close", "marker")}
            with self.assertRaises(SourceLiveRunFailed) as failure:
                _finish_enrollment(None, False, steps["dispose"], steps["close"], steps["marker"])
            self.assertEqual(str(failure.exception), "enrollment-cleanup-failed; cleanup=enrollment-cleanup-failed")
            if failing_phase != "marker":
                steps["marker"].assert_not_called()

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
