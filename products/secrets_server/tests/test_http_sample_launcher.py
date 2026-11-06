"""Secrets product binding and the actual import-safe launcher composition."""
from dataclasses import replace
import importlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.http_verification_sample_installation import (
    HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT as SAMPLE_ENV,
    HttpVerificationSampleReceiverConfigurationCodec,
)
from control_plane_kit_secrets.bootstrap import ProviderConfigurationError
from secrets_control_fixtures import configuration
from scripts.http_sample_fixture import SampleAuthority


class SecretsHttpSampleLauncherTests(unittest.TestCase):
    def setUp(self):
        self.owner = importlib.import_module("control_plane_kit_servers_secrets_server.configuration")
        self.launcher = importlib.import_module("control_plane_kit_servers_secrets_server.server")
        self.control = configuration()
        self.artifact = self.owner.secrets_control_configuration_artifact(self.control)
        self.ordinary = self.owner.secrets_source_runtime_contract(self.artifact)
        self.authority = SampleAuthority(self.control, self.ordinary)
        self.samples = self.owner.secrets_http_sample_configuration_artifact(self.control, self.authority.configuration)

    def test_companion_preserves_original_product_and_rejects_receiver_crosswire(self):
        actual = self.owner.secrets_source_runtime_contract(self.artifact, sample_artifact=self.samples)
        self.assertEqual(actual.configuration_artifacts, (self.artifact, self.samples))
        self.assertEqual(replace(actual, configuration_artifacts=self.ordinary.configuration_artifacts,
            public_environment=self.ordinary.public_environment), self.ordinary)
        self.assertIn(PublicStaticEnvironmentBinding(SAMPLE_ENV, self.samples.target_path), actual.public_environment)
        binding = self.owner.secrets_http_sample_binding(self.control, self.authority.configuration)
        self.assertEqual([(entry.check, entry.container_port) for entry in binding.checks], [(self.authority.check,8081)])
        crossed = replace(self.authority.configuration, target=replace(self.control.target, receiver_id="f" * 32))
        self.assertEqual(core.receiver_node_control_audience(crossed.target), binding.audience)
        crossed_raw = HttpVerificationSampleReceiverConfigurationCodec().encode_canonical_bytes(crossed)
        for invalid in (replace(self.samples, artifact_id="other"), replace(self.samples, target_path="/etc/other.json"),
                replace(self.samples, content=crossed_raw.decode()), replace(self.samples, content="{}")):
            with self.subTest(artifact=invalid.artifact_id):
                with self.assertRaises(self.owner.SecretsProductConfigurationError):
                    self.owner.secrets_source_runtime_contract(self.artifact, sample_artifact=invalid)

    def test_launcher_passes_one_independent_snapshot_and_binding_to_real_factory_boundary(self):
        with TemporaryDirectory() as directory:
            control_path = Path(directory) / "control.json"
            sample_path = Path(directory) / "samples.json"
            control_path.write_text(self.artifact.content)
            sample_path.write_text(self.samples.content)
            control_path.chmod(0o444)
            sample_path.chmod(0o444)
            with patch.dict(os.environ, {"CPK_WRAPPER_CONFIGURATION_FILE":str(control_path), SAMPLE_ENV:str(sample_path)}), \
                    patch.object(self.launcher.application, "app_from_environment") as factory:
                sentinel = factory.return_value
                self.assertIs(self.launcher.create_app(http_sample_clock=lambda:150.25), sentinel)
                factory.assert_called_once()
                call = factory.call_args.kwargs
                self.assertEqual(call["control"], self.control)
                self.assertEqual(call["http_verification_binding"],
                    self.owner.secrets_http_sample_binding(self.control, self.authority.configuration))
                self.assertEqual(call["http_sample_clock"](),150.25)
                factory.reset_mock()
                sample_path.chmod(0o644)
                sample_path.write_text("malformed-public-companion")
                sample_path.chmod(0o444)
                with self.assertRaises(ProviderConfigurationError):
                    self.launcher.create_app()
                factory.assert_not_called()
                sample_path.unlink()
                with self.assertRaises(ProviderConfigurationError):
                    self.launcher.create_app()
                factory.assert_not_called()
            with patch.dict(os.environ, {"CPK_WRAPPER_CONFIGURATION_FILE":str(control_path)}), \
                    patch.object(self.launcher.application, "app_from_environment") as factory:
                self.launcher.create_app()
                self.assertIsNone(factory.call_args.kwargs["http_verification_binding"])
                self.assertEqual(factory.call_args.kwargs["control"], self.control)
