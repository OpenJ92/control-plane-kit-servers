"""Product author takes public trust and derives the independent original pair."""
from dataclasses import replace
import unittest

import control_plane_kit_core as core
from control_plane_kit_core.http_verification_sample_installation import (
    HttpVerificationSampleVerifierConfiguration, HttpVerificationSampleReceiverConfigurationCodec,
)
from control_plane_kit_core.http_verification_samples import http_verification_check_digest
from control_plane_kit_servers_secrets_server import configuration as owner
from secrets_control_fixtures import SourceControlAuthority


class SecretsFullHttpSampleCompanionTests(unittest.TestCase):
    def setUp(self):
        authority = SourceControlAuthority()
        self.control = authority.configuration()
        self.verifier = HttpVerificationSampleVerifierConfiguration(
            core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE,
            "independently-supplied-test-issuer", authority.health_keys.public_keys)
        self.ordinary = owner.secrets_source_runtime_contract(owner.secrets_control_configuration_artifact(self.control))

    def test_full_author_preserves_supplied_public_trust_and_both_original_checks(self):
        artifact = owner.secrets_full_http_sample_configuration_artifact(self.control, self.verifier)
        configured = HttpVerificationSampleReceiverConfigurationCodec().decode_canonical_bytes(artifact.content.encode())
        self.assertEqual(configured.verifier, self.verifier)
        self.assertEqual(configured.target, self.control.target)
        self.assertEqual(configured.declaration_identity, self.control.declaration.identity().value)
        self.assertEqual([(entry.check_id, entry.check_digest) for entry in configured.checks],
            [(check.check_id, http_verification_check_digest(check)) for check in self.ordinary.verification.checks])
        self.assertEqual([entry.check_digest for entry in configured.checks], [
            "5911cb3dce76dacd9bdea52d33cc07fb8879fb6318a826cf64653316ae3920b7",
            "9168b2fe37d83e63062a3d22be950b90b3be48062755744ff70879c5c0538b1f"])
        actual = owner.secrets_source_runtime_contract(self.ordinary.configuration_artifacts[0], sample_artifact=artifact)
        self.assertEqual(replace(actual, configuration_artifacts=self.ordinary.configuration_artifacts,
            public_environment=self.ordinary.public_environment), self.ordinary)
        self.assertEqual([(entry.check.check_id, entry.container_port)
            for entry in owner.secrets_http_sample_binding(self.control, configured).checks], [("live", 8081), ("ready", 8081)])

    def test_general_receiver_still_accepts_an_explicit_checked_subset(self):
        full = owner.secrets_full_http_sample_configuration_artifact(self.control, self.verifier)
        configured = HttpVerificationSampleReceiverConfigurationCodec().decode_canonical_bytes(full.content.encode())
        subset = replace(configured, checks=(configured.checks[1],))
        artifact = owner.secrets_http_sample_configuration_artifact(self.control, subset)
        self.assertEqual(owner.secrets_http_sample_binding(self.control, subset).checks[0].check.check_id, "ready")
        self.assertEqual(owner.secrets_source_runtime_contract(self.ordinary.configuration_artifacts[0],
            sample_artifact=artifact).verification, self.ordinary.verification)

    def test_invalid_or_forged_public_inputs_have_fixed_redacted_refusal(self):
        forged = replace(self.verifier)
        object.__setattr__(forged, "issuer", "invalid issuer marker")
        for control, verifier in ((None, self.verifier), (self.control, None), (self.control, forged)):
            with self.subTest(control=control is None), self.assertRaises(owner.SecretsProductConfigurationError) as caught:
                owner.secrets_full_http_sample_configuration_artifact(control, verifier)
            self.assertEqual(str(caught.exception), "Secrets product control configuration is invalid")
            self.assertIsNone(caught.exception.__context__)
            self.assertIsNone(caught.exception.__cause__)

    def test_crosswired_full_companion_cannot_replace_independent_control(self):
        other = replace(self.control, target=replace(self.control.target, receiver_id="f" * 32))
        artifact = owner.secrets_full_http_sample_configuration_artifact(other, self.verifier)
        with self.assertRaises(owner.SecretsProductConfigurationError):
            owner.secrets_source_runtime_contract(self.ordinary.configuration_artifacts[0], sample_artifact=artifact)
