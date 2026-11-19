"""Two qualified public-sample laws over the current receiver test fixtures."""
from dataclasses import replace
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
import control_plane_kit_core as core
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.http_verification_sample_installation import (
    HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT,
    HttpVerificationSampleReceiverConfiguration, HttpVerificationSampleVerifierConfiguration,
    HttpVerificationSampleCheckBinding, HttpVerificationSampleReceiverConfigurationCodec,
)
from control_plane_kit_core.http_verification_samples import http_verification_check_digest
from control_plane_kit_core.products import ProviderRuntimePort
from test_control_receiver import CpkControlReceiverTests


class SampleAuthority:
    """Only the historical fixture's ephemeral public configuration constructor."""
    def __init__(self, control, contract):
        self.check, = (check for check in contract.verification.checks if check.check_id == "ready")
        private = Ed25519PrivateKey.generate()
        public = core.DelegationPublicKey("source-sample", core.DelegationKeyAlgorithm.ED25519,
            private.public_key().public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii"))
        self.configuration = HttpVerificationSampleReceiverConfiguration(control.target,
            control.declaration.identity().value, HttpVerificationSampleVerifierConfiguration(
                core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE, "source-sample-witness", (public,)),
            (HttpVerificationSampleCheckBinding("ready", http_verification_check_digest(self.check)),))


class GrandparentSampleAdmissionTests(CpkControlReceiverTests):
    # The runner selects only these two historical laws. All ordinary inherited
    # receiver laws run unchanged in the common owner-test selection instead.
    def test_optional_samples_bind_original_metadata_and_preserve_ordinary_contract(self):
        baseline = self.config.cpk_source_runtime_contract(self.config.CpkSourceVariant.CPK, self.artifact)
        authority = SampleAuthority(self.control, baseline)
        artifact = self.config.cpk_http_sample_configuration_artifact(self.control, authority.configuration)
        for variant in self.config.CpkSourceVariant:
            ordinary = self.config.cpk_source_runtime_contract(variant, self.artifact)
            supplied = self.config.cpk_source_runtime_contract(variant, self.artifact, sample_artifact=artifact)
            self.assertEqual(supplied.configuration_artifacts, (self.artifact, artifact))
            self.assertEqual(replace(supplied, configuration_artifacts=ordinary.configuration_artifacts,
                public_environment=ordinary.public_environment), ordinary)
            self.assertIn(PublicStaticEnvironmentBinding(HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT,
                artifact.target_path), supplied.public_environment)
        binding = self.config.cpk_http_sample_binding(self.control, authority.configuration)
        self.assertEqual([(entry.check, entry.container_port) for entry in binding.checks], [(authority.check, 8080)])
        crossed = replace(authority.configuration, target=replace(self.control.target, receiver_id="f" * 32))
        self.assertEqual(core.receiver_node_control_audience(crossed.target), binding.audience)
        crossed_bytes = HttpVerificationSampleReceiverConfigurationCodec().encode_canonical_bytes(crossed)
        for invalid in (replace(artifact, artifact_id="other"), replace(artifact, target_path="/etc/other.json"),
                replace(artifact, content=crossed_bytes.decode()), replace(artifact, content="{}")):
            self.rejected(lambda: self.config.cpk_source_runtime_contract(
                self.config.CpkSourceVariant.CPK, self.artifact, sample_artifact=invalid))
        changed = replace(binding, provider_ports=(ProviderRuntimePort("http-api", 8081),
            ProviderRuntimePort("mcp", 8080)))
        with patch.object(self.server, "_operations_application") as operations:
            self.rejected(lambda: self.server.create_app(self.bootstrap, self.verifier,
                control=self.control, http_verification_binding=changed))
            operations.assert_not_called()

    def test_actual_main_reads_optional_public_companion_before_operations(self):
        ordinary = self.config.cpk_source_runtime_contract(self.config.CpkSourceVariant.CPK, self.artifact)
        authority = SampleAuthority(self.control, ordinary)
        artifact = self.config.cpk_http_sample_configuration_artifact(self.control, authority.configuration)
        with TemporaryDirectory() as directory:
            path = Path(self.config.HTTP_SAMPLE_SLOT.target_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.assertFalse(path.exists())
            self.addCleanup(path.unlink, missing_ok=True)
            path.write_text(artifact.content)
            path.chmod(0o444)
            with patch.dict(os.environ, {HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT: str(path)}), \
                    patch.object(self.server.CpkServerBootstrapConfiguration, "from_environment", return_value=self.bootstrap) as bootstrap, \
                    patch.object(self.server, "_credential_verifier", return_value=self.verifier) as verifier, \
                    patch.object(self.server, "_configured_principal_authorizer", return_value=None), \
                    patch.object(self.server, "read_cpk_control_configuration", return_value=self.control), \
                    patch.object(self.server, "_operations_application", return_value=self.server.CpkServerOperationsApplication(self.services)) as operations, \
                    patch.object(self.server.uvicorn, "run") as run:
                self.assertEqual(self.server.main(), 0)
                operations.assert_called_once()
                with TestClient(run.call_args.args[0]) as client:
                    self.assertEqual(client.get("/__control/verification/http").status_code, 401)
                    self.assertEqual(client.get("/health/ready").status_code, 200)
                operations.reset_mock()
                run.reset_mock()
                bootstrap.reset_mock()
                verifier.reset_mock()
                wrong = Path(directory) / "samples.json"
                wrong.write_text(artifact.content)
                wrong.chmod(0o444)
                from control_plane_kit_server_sdk import wrapper
                # Presence is the opt-in: empty values also refuse before the
                # generic reader or protected bootstrap, never falling back.
                for selected_path in (str(wrong), ""):
                    with self.subTest(selected_path=selected_path), \
                            patch.dict(os.environ, {HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT: selected_path}), \
                            patch.object(wrapper, "load_http_verification_sample_configuration") as reader:
                        self.assertEqual(self.server.main(), 2)
                        reader.assert_not_called()
                    bootstrap.assert_not_called()
                    verifier.assert_not_called()
                    operations.assert_not_called()
                    run.assert_not_called()
                path.chmod(0o644)
                path.write_text("malformed-public-companion")
                path.chmod(0o444)
                self.assertEqual(self.server.main(), 2)
                bootstrap.assert_not_called()
                verifier.assert_not_called()
                operations.assert_not_called()
                run.assert_not_called()
