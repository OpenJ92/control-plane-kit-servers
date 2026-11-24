"""Exercise the source smoke's signed requests without starting either product."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
import jwt

import control_plane_kit_core as core
from control_plane_kit_core.http_verification_sample_installation import HttpVerificationSampleReceiverConfigurationCodec
from control_plane_kit_core.http_verification_samples import (
    HttpVerificationSampleGrantCodec, HttpVerificationSampleResult, http_verification_check_digest,
)
from control_plane_kit_core.verification import HttpVerificationEvidence, VerificationOutcome
from control_plane_kit_servers_cpk_server import control_configuration as cpk
from control_plane_kit_servers_secrets_server import configuration as secrets
from products.cpk_server.tests.cpk_http_host_fixtures import fixture
from products.secrets_server.tests.secrets_control_fixtures import configuration
from scripts.http_sample_fixture import SampleAuthority, witness


class SignedHttpSampleWitnessTests(unittest.TestCase):
    def test_ready_alone_is_insufficient_for_the_source_smoke(self):
        control = configuration()
        contract = secrets.secrets_source_runtime_contract(secrets.secrets_control_configuration_artifact(control))
        ready, = (check for check in contract.verification.checks if check.check_id == "ready")
        ready_only = replace(contract, verification=replace(contract.verification, checks=(ready,)))
        with self.assertRaises(ValueError):
            SampleAuthority(control, ready_only, all_checks=True)

    def exercise(self, product, *, substitute=False):
        if product == "cpk":
            control = fixture().config
            artifact = cpk.cpk_control_configuration_artifact(control)
            contract = cpk.cpk_source_runtime_contract(cpk.CpkSourceVariant.CPK, artifact)
            listener, socket = "http://cpk-source:8080", "http-api"
        else:
            control = configuration()
            artifact = secrets.secrets_control_configuration_artifact(control)
            contract = secrets.secrets_source_runtime_contract(artifact)
            listener, socket = "http://secrets-provider:8081", "control"
        checks = {check.check_id: check for check in contract.verification.checks}
        expected = {name: http_verification_check_digest(check) for name, check in checks.items()}
        self.assertEqual(set(checks), {"live", "ready"})
        self.assertEqual(len(set(expected.values())), 2)
        observed = []
        request_ids = set()

        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "control.json").write_text(artifact.content)
            (directory / "sample.ready").touch()

            @contextmanager
            def exchange(method, url, *, headers, timeout, trust_env):
                self.assertEqual((method, url), ("GET", listener + "/__control/verification/http"))
                self.assertEqual(headers["Accept-Encoding"], "identity")
                self.assertFalse(trust_env)
                installed = HttpVerificationSampleReceiverConfigurationCodec().decode_canonical_bytes(
                    (directory / "http-samples.json").read_bytes())
                verifier = installed.verifier
                claims = jwt.decode(headers["Authorization"].removeprefix("Bearer "),
                    verifier.public_keys[0].public_key_pem, algorithms=["EdDSA"],
                    issuer=verifier.issuer, audience=core.receiver_node_control_audience(control.target))
                request = HttpVerificationSampleGrantCodec().decode(claims["workload_http_verification_sample"]).request
                check = checks[request.check_id]
                self.assertEqual((request.target, check.provider_socket, request.check_digest),
                    (control.target, socket, expected[check.check_id]))
                observed.append(check.check_id)
                request_ids.add(request.request_id)
                if substitute and check.check_id == "live":
                    check = checks["ready"]
                    request = replace(request, check_id="ready", check_digest=expected["ready"])
                result = HttpVerificationSampleResult(request, VerificationOutcome.PASSED,
                    HttpVerificationEvidence(200, 5))
                yield httpx.Response(200, stream=httpx.ByteStream(result.canonical_bytes(installed_check=check)))

            with patch("scripts.http_sample_fixture.httpx.stream", exchange):
                if substitute:
                    with self.assertRaises(ValueError):
                        witness(product, directory)
                    self.assertIn("live", observed)
                    self.assertFalse((directory / "sample.passed").exists())
                    return
                witness(product, directory)
            installed = HttpVerificationSampleReceiverConfigurationCodec().decode_canonical_bytes(
                (directory / "http-samples.json").read_bytes())
            self.assertEqual({entry.check_id: entry.check_digest for entry in installed.checks}, expected)
            self.assertCountEqual(observed, ["live", "ready"])
            self.assertEqual(len(request_ids), 2)
            self.assertTrue((directory / "sample.passed").is_file())

    def test_both_declared_checks_are_signed_and_correlated(self):
        for product in ("cpk", "secrets"):
            with self.subTest(product=product):
                self.exercise(product)

    def test_ready_result_substituted_for_live_is_refused(self):
        for product in ("cpk", "secrets"):
            with self.subTest(product=product):
                self.exercise(product, substitute=True)
