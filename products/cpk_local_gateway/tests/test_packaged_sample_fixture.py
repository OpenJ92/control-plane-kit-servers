"""Gateway fixture laws, not packaged child or approved execution evidence.

The real gateway ASGI implementation runs. Its child HTTP responses are explicit
external doubles; recording their authorization gives public wire booleans only.
"""
from collections import Counter
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest

import httpx
import jwt
import control_plane_kit_core as core
from control_plane_kit_core.http_verification_sample_installation import HttpVerificationSampleReceiverConfigurationCodec
from control_plane_kit_core.http_verification_samples import (
    HttpVerificationSampleRequestCodec, HttpVerificationSampleResult, http_verification_check_digest,
)
from control_plane_kit_core.verification import VerificationOutcome, HttpVerificationEvidence
from control_plane_kit_servers_cpk_local_gateway.http_sample_relay import GatewayHttpSampleRelay
from control_plane_kit_servers_cpk_local_gateway.health_relay import GatewayHealthRelay
from control_plane_kit_servers_cpk_local_gateway.health_transit_verification import gateway_health_transit_verifier_from_artifact
from control_plane_kit_servers_cpk_local_gateway import server
from packaged_sample_fixture import GatewaySampleFixture


class PackagedSampleFixtureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = GatewaySampleFixture(clock=lambda:150)

    def test_public_artifacts_keep_original_pairs_and_separate_transit_trust(self):
        fixture = self.fixture
        self.assertNotEqual(fixture.workload_public.fingerprint_sha256, fixture.transit_public.fingerprint_sha256)
        for role, receiver in fixture.receivers.items():
            self.assertEqual(tuple(check.check_id for check in receiver.contract.verification.checks), ("live", "ready"))
            companion = HttpVerificationSampleReceiverConfigurationCodec().decode_canonical_bytes(receiver.artifacts[1].content.encode())
            self.assertEqual(companion.target, receiver.control.target)
            self.assertEqual(companion.declaration_identity, receiver.control.declaration.identity().value)
            self.assertEqual(companion.verifier.public_keys, (fixture.workload_public,))
            self.assertEqual(tuple((value.check_id, value.check_digest) for value in companion.checks),
                tuple((check.check_id, http_verification_check_digest(check)) for check in receiver.contract.verification.checks))
        self.assertEqual(len(fixture.routes.targets), 2)
        with TemporaryDirectory() as root:
            public = Path(root) / "public"
            fixture.write(public)
            paths = tuple(path for path in public.rglob("*") if path.is_file())
            self.assertEqual(len(paths), 9)
            for path in paths:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertNotIn(b"PRIVATE KEY", path.read_bytes())
                self.assertNotIn(b"Bearer ", path.read_bytes())
            with self.assertRaises(FileExistsError):
                fixture.write(public)

    def test_wrong_transit_purpose_preserves_other_transit_authority_fields(self):
        fixture = self.fixture
        request = fixture.request("cpk", fixture.receivers["cpk"].contract.verification.checks[0])
        control = fixture.token(request, transit=True)
        candidate = fixture.token(request, transit=True,
            purpose=core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE)
        self.assertTrue(jwt.get_unverified_header(control) == jwt.get_unverified_header(candidate))
        def claims(token):
            # Both signatures must validate against the transit key, while the
            # fixed synthetic clock deliberately differs from the host clock.
            value = jwt.decode(token, fixture.transit_public.public_key_pem, algorithms=["EdDSA"],
                options={"verify_exp":False, "verify_iat":False, "verify_nbf":False, "verify_aud":False})
            value.pop("jti")
            grant = value["gateway_http_verification_sample_transit"]
            grant.pop("jti")
            purpose = grant.pop("purpose")
            return value, purpose
        control_claims, control_purpose = claims(control)
        candidate_claims, candidate_purpose = claims(candidate)
        self.assertTrue(control_claims == candidate_claims)
        self.assertEqual(control_purpose, core.DelegationKeyPurpose.GATEWAY_HTTP_VERIFICATION_SAMPLE_TRANSIT.value)
        self.assertEqual(candidate_purpose, core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE.value)

    async def test_actual_gateway_forwards_workload_only_and_distinguishes_refusal_paths(self):
        fixture = self.fixture
        observed = []
        health_observed = []
        def clean_wire(request, receiver, path, credential):
            # Boolean assertions deliberately exclude bearer-bearing values
            # from failure output. Check every permitted header, not just auth.
            expected = {"host":httpx.URL(receiver.origin).netloc.decode("ascii"),
                "accept":"application/json", "accept-encoding":"identity",
                "connection":"keep-alive", "user-agent":"python-httpx/" + httpx.__version__,
                "authorization":"Bearer " + credential}
            clean = (request.method == "GET" and str(request.url) == receiver.origin + path
                and request.url.query == b"" and request.content == b""
                and len(request.headers.raw) == len(expected)
                and dict(request.headers) == expected)
            self.assertTrue(clean, "outbound request exceeded the workload-only wire contract")
            return clean
        def child(request):
            # Observe only public facts, never retain an authorization value.
            credential = request.headers.get("authorization", "").removeprefix("Bearer ")
            header = jwt.get_unverified_header(credential)
            is_health = request.url.path == "/__control/health/liveness"
            public = fixture.health_public if is_health else fixture.workload_public
            payload = jwt.decode(credential, public.public_key_pem, algorithms=["EdDSA"],
                options={"verify_exp":False, "verify_iat":False, "verify_nbf":False, "verify_aud":False})
            if is_health:
                grant = core.DelegatedWorkloadReceiverHealthReadGrantCodec().decode(payload["workload_node_health_read"])
                role, receiver = next((role, value) for role, value in fixture.receivers.items()
                    if value.control.target == grant.target)
                supplied = core.ReceiverHealthReadRequest(grant.target, grant.authority_context,
                    grant.kind, grant.declaration_identity, grant.request_id)
                wire_clean = clean_wire(request, receiver, "/__control/health/liveness", credential)
                self.assertEqual(header["typ"], "CPK-WORKLOAD-NODE-HEALTH-READ+JWT")
                self.assertEqual(header["kid"], fixture.health_public.key_id)
                self.assertEqual(grant.kind, core.NodeHealthReadKind.LIVENESS)
                self.assertEqual(grant.request_digest, supplied.canonical_digest())
                health_observed.append(dict(role=role, workload_signature=True, workload_only_wire=wire_clean))
                result = core.ReceiverHealthReadResult(supplied, receiver.control.declaration,
                    core.NodeHealthReadOutcome.HEALTHY)
                return httpx.Response(200, content=result.canonical_bytes(), headers={"Content-Type":"application/json"})
            supplied = HttpVerificationSampleRequestCodec().decode(payload["workload_http_verification_sample"]["request"])
            receiver = fixture.receivers[supplied.route_id]
            check, = (value for value in receiver.contract.verification.checks if value.check_id == supplied.check_id)
            wire_clean = clean_wire(request, receiver, "/__control/verification/http", credential)
            self.assertTrue(header["typ"] == "CPK-WORKLOAD-HTTP-VERIFICATION-SAMPLE+JWT")
            self.assertTrue(header["kid"] == fixture.workload_public.key_id)
            foreign = payload["iss"] == "foreign-source-witness"
            observed.append(dict(role=supplied.route_id, check_id=supplied.check_id, foreign=foreign,
                workload_signature=True, workload_only_wire=wire_clean))
            # Explicit external HTTP reply fixture: this does not implement or
            # establish a child SDK authorization/health decision.
            if foreign:
                return httpx.Response(401, json={"code":"fixture-child-refused"})
            result = HttpVerificationSampleResult(supplied, VerificationOutcome.PASSED, HttpVerificationEvidence(200, 0))
            return httpx.Response(200, content=result.canonical_bytes(installed_check=check),
                headers={"Content-Type":"application/json"})
        relay = GatewayHttpSampleRelay(fixture.routes, fixture.transit_trust,
            clock=fixture.clock, transport=httpx.MockTransport(child))
        health_relay = GatewayHealthRelay(fixture.routes,
            gateway_health_transit_verifier_from_artifact(fixture.gateway_artifacts[0]),
            clock=fixture.clock, transport=httpx.MockTransport(child))
        app = server.create_app(http_sample_relay=relay, health_relay=health_relay)
        receipt = await fixture.exercise(transport=httpx.ASGITransport(app=app))
        self.assertEqual(len(receipt["samples"]), 4)
        self.assertEqual(Counter((value["role"], value["check_id"], value["foreign"]) for value in observed),
            Counter((role, check, foreign) for role in ("cpk", "secrets") for check in ("live", "ready") for foreign in (False, True)))
        for value in observed:
            self.assertTrue(value["workload_signature"] and value["workload_only_wire"])
        self.assertEqual(Counter(value["role"] for value in health_observed), Counter(("cpk", "secrets")))
        for value in health_observed:
            self.assertTrue(value["workload_signature"] and value["workload_only_wire"])
        self.assertEqual(len(receipt["health_relays"]), 2)
        for value in receipt["health_relays"]:
            self.assertEqual(value["kind"], "liveness")
            self.assertEqual(value["http_transit_refused"], 401)
            self.assertEqual(value["v2_transit_refused_for_http"], 401)
        self.assertFalse(receipt["approved_run"])
        self.assertEqual(receipt["child_health_probe_count"], "not-observed")
        for sample in receipt["samples"]:
            for refusal in sample["refusals"].values():
                self.assertEqual(refusal["forwarding"], "not-observed")
                self.assertEqual(refusal["child_refusal"], "not-observed")
            self.assertEqual({name:value["status"] for name, value in sample["refusals"].items()}, {
                "missing_transit":401, "foreign_transit_issuer":401, "wrong_transit_purpose":401,
                "unknown_selector":403, "expired_transit":504, "expired_workload":504,
                "crossed_selector":403, "crossed_workload_target":403, "crossed_workload_check":403,
                "foreign_workload_issuer":502})
