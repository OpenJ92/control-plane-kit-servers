"""One real SDK sample, with an explicit caller fixture and provenance receipt."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import importlib.util
from importlib import metadata
import hashlib
import json
import os
from pathlib import Path
from threading import Thread
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
import httpx
import jwt
import control_plane_kit_core as core
from control_plane_kit_core.algebra import ProviderSocket
from control_plane_kit_core.products import ProviderRuntimePort
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration
from control_plane_kit_core.verification import HttpCheck, VerificationContract, VerificationPolicy, VerificationOutcome
from control_plane_kit_core.http_verification_samples import (
    HttpVerificationSampleRequest, HttpVerificationSampleGrant, HttpVerificationSampleResult,
    HttpVerificationSampleResultCodec, http_verification_check_digest,
)
from control_plane_kit_core.http_verification_sample_installation import (
    HttpVerificationSampleReceiverBinding, HttpVerificationSampleReceiverConfiguration,
    HttpVerificationSampleVerifierConfiguration, HttpVerificationSampleCheckBinding,
)
from control_plane_kit_server_sdk.fastapi import install_cpk_wrapper

MODULE = "control_plane_kit_servers_cpk_local_gateway.http_sample_relay"


def key(name):
    private = Ed25519PrivateKey.generate()
    pem = private.public_key().public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    return private, core.DelegationPublicKey(name, core.DelegationKeyAlgorithm.ED25519, pem)


class Fixture:
    def __init__(self, port):
        roles = core.NodeControlGraphReferenceRole
        self.target = core.NodeControlReceiverTarget(*(
            core.NodeControlGraphReference(role, value) for role, value in (
                (roles.WORKSPACE, "workspace-a"), (roles.RUNTIME, "runtime-a"),
                (roles.NODE, "child"), (roles.PROVIDER_SOCKET, "control"))), "a" * 32)
        self.gateway = replace(self.target, node_id=replace(self.target.node_id, value="gateway"),
            receiver_id="b" * 32)
        self.declaration = core.WorkloadNodeControlSurfaceDeclaration(
            core.WorkloadNodeControlSurfaceDescriptor(self.target.provider_socket_name, (),
                health_reads=(core.NodeHealthReadKind.LIVENESS,)),
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)
        self.g_private, self.g_key = key("gateway-key")
        self.w_private, self.w_key = key("workload-key")
        receiver = core.ReceiverNodeControlConfiguration(self.target, self.declaration, tuple(
            NodeControlVerificationConfiguration(purpose, "controller", (self.w_key,))
            for purpose in (core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
                            core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)))
        self.check = HttpCheck(check_id="ready", provider_socket="control", path="/health/ready",
            policy=VerificationPolicy(timeout_seconds=1, maximum_attempts=1, maximum_evidence_bytes=32))
        configuration = HttpVerificationSampleReceiverConfiguration(self.target,
            self.declaration.identity().value, HttpVerificationSampleVerifierConfiguration(
                core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE, "controller", (self.w_key,)),
            (HttpVerificationSampleCheckBinding("ready", http_verification_check_digest(self.check)),))
        self.binding = HttpVerificationSampleReceiverBinding(configuration, receiver,
            VerificationContract((self.check,)), (ProviderSocket("control", Protocol.HTTP),),
            (ProviderRuntimePort("control", port),))
        self.request = HttpVerificationSampleRequest(target=self.target,
            authority_context=core.NodeControlAuthorityContext("graph-a", "projection-a"),
            declaration_identity=self.declaration.identity().value, gateway_target=self.gateway,
            route_id="child-route", run_id="run-a", activity_id="activity-a", outer_attempt=1,
            effect_id="effect-a", request_fingerprint="c" * 64, check_id="ready",
            check_digest=http_verification_check_digest(self.check), sample_ordinal=1, request_id="request-a")
        route = core.ReceiverManagementRouteBinding("child-route", self.target,
            self.declaration, f"http://configured-child:{port}")
        self.routes = core.ReceiverManagementRoutes(self.gateway, (route,))

    def grant(self, *, gateway=False, request=None, purpose=None, audience=None):
        public = self.g_key if gateway else self.w_key
        role = (core.DelegationKeyPurpose.GATEWAY_HTTP_VERIFICATION_SAMPLE_TRANSIT if gateway
                else core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE)
        return HttpVerificationSampleGrant(request=request or self.request, purpose=purpose or role,
            issuer="controller", key_id=public.key_id,
            audience=audience or ("gateway:workspace-a:gateway" if gateway else self.binding.audience),
            issued_at=145, not_before=145, expires_at=160, jti="gateway-jti" if gateway else "workload-jti")

    def credential(self, *, gateway=False, **options):
        private, public = (self.g_private, self.g_key) if gateway else (self.w_private, self.w_key)
        grant = self.grant(gateway=gateway, **options)
        prefix = "GATEWAY-HTTP-VERIFICATION-SAMPLE-TRANSIT" if gateway else "WORKLOAD-HTTP-VERIFICATION-SAMPLE"
        claim = "gateway_http_verification_sample_transit" if gateway else "workload_http_verification_sample"
        return jwt.encode(dict(iss=grant.issuer, aud=grant.audience, iat=grant.issued_at,
            nbf=grant.not_before, exp=grant.expires_at, jti=grant.jti, **{claim: grant.descriptor()}),
            private, algorithm="EdDSA", headers={"typ": "CPK-" + prefix + "+JWT", "kid": public.key_id})

    def envelope(self, workload, **changes):
        return {"profile": "cpk-gateway-http-verification-sample-request.v1",
            "target_id": self.request.route_id, "request": self.request.descriptor(),
            "workload_credential": workload, **changes}

    def receiver(self):
        app = FastAPI()
        install_cpk_wrapper(app, configuration=self.binding.receiver_configuration,
            clock=lambda: 150, http_sample_clock=lambda: 150, http_verification_binding=self.binding)
        return app


@contextmanager
def ready_endpoint():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, self.headers.get("Authorization")))
            self.send_response(200)
            self.send_header("Content-Length", "5")
            self.end_headers()
            self.wfile.write(b"ready")
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield server.server_port, calls
    finally:
        server.shutdown()
        thread.join(3)
        server.server_close()


class HttpSampleRelayTests(unittest.IsolatedAsyncioTestCase):
    def relay(self, fixture, transport):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "HTTP sample relay interface is missing")
        api = importlib.import_module(MODULE)
        relay = api.GatewayHttpSampleRelay(configuration=fixture.routes,
            trust=api.GatewayHttpSampleTrust(fixture.gateway, "controller", (fixture.g_key,)),
            clock=lambda: 150, transport=transport)
        server = importlib.import_module("control_plane_kit_servers_cpk_local_gateway.server")
        return server.create_app(http_sample_relay=relay)

    async def supplied_test_sender(self, app, fixture, workload, *, token=None, envelope=None):
        # This caller is intentionally credited as a test sender, not I148.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            return await client.post("/cpk/verification/http", content=json.dumps(
                envelope or fixture.envelope(workload), sort_keys=True, separators=(",", ":")).encode(),
                headers={"Authorization": "Bearer " + (token or fixture.credential(gateway=True)),
                         "Content-Type": "application/json"})

    async def test_one_real_ready_sample_and_workload_only_child_get(self):
        with ready_endpoint() as (port, ready_calls):
            fixture = Fixture(port)
            workload = fixture.credential()
            gateway = fixture.credential(gateway=True)
            child_calls = []
            sdk = httpx.ASGITransport(app=fixture.receiver())
            async def child(request):
                self.assertEqual((request.url.scheme, request.url.host, request.url.port),
                                 ("http", "configured-child", port))
                authorization = request.headers.get_list("authorization")
                child_calls.append((request.method, request.url.path, request.url.query,
                    await request.aread(), authorization == ["Bearer " + workload],
                    all(gateway not in item for item in authorization)))
                return await sdk.handle_async_request(request)
            app = self.relay(fixture, httpx.MockTransport(child))
            # Both modes assert the same SDK observation below. The opt-in mode
            # additionally proves actual reviewed sender dispatch and provenance;
            # the ordinary mode remains honestly credited as a supplied caller.
            if "CPK_REVIEWED_HTTP_SAMPLE_SENDER" in os.environ:
                result = await self.reviewed_sender(app, fixture, workload, gateway)
            else:
                response = await self.supplied_test_sender(app, fixture, workload, token=gateway)
                self.assertEqual(response.status_code, 200)
                self.assertLessEqual(len(response.content), 2048)
                result = HttpVerificationSampleResultCodec(fixture.request, fixture.check).decode_canonical_bytes(response.content)
            self.assertIs(result.outcome, VerificationOutcome.PASSED)
            self.assertEqual(result.evidence.status_code, 200)
            self.assertEqual(child_calls, [("GET", "/__control/verification/http", b"", b"", True, True)])
            self.assertEqual(ready_calls, [("/health/ready", None)])

    async def reviewed_sender(self, app, fixture, workload, gateway):
        revision = "d5765cdffb4c2a02d4be9b81b401e96c17e4624b"
        self.assertEqual(os.environ["CPK_REVIEWED_HTTP_SAMPLE_SENDER"], revision)
        api = importlib.import_module("control_plane_kit_interpreters.probes.http_sample_transport")
        source = Path(api.__file__).resolve()
        self.assertEqual(str(source), "/reviewed-sender/src/control_plane_kit_interpreters/probes/http_sample_transport.py")
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         "086144625bf8b30cbd7dbf0277a5db2a0db08ef9f133e9686275e3f284b576c6")
        from control_plane_kit_core.public_ingress import (
            IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget,
        )
        dns_calls, outer_calls = [], []
        class PublicResolver:
            async def resolve(self, hostname):
                dns_calls.append(hostname)
                return ("8.8.8.8",)
        outer = httpx.ASGITransport(app=app)
        async def forward(request):
            self.assertEqual((request.method, str(request.url)),
                             ("POST", "https://8.8.8.8/cpk/verification/http"))
            self.assertEqual(request.headers["host"], "gateway.example.invalid:443")
            self.assertEqual(request.extensions["sni_hostname"], "gateway.example.invalid")
            self.assertEqual(request.headers["authorization"], "Bearer " + gateway)
            outer_calls.append(True)
            return await outer.handle_async_request(request)
        destination = api.SelectedHttpSampleGateway(
            NamedPublicIngress("management", IngressAuthorityReference("synthetic-authority"),
                PublicIngressTarget("gateway", "transit"), "connector", "gateway.example.invalid"),
            fixture.gateway, fixture.routes.targets[0], "transit")
        credentials = api.SignedHttpSampleCredentials(gateway.encode("ascii"), workload.encode("ascii"),
                                                     fixture.grant(gateway=True), fixture.grant())
        client = api.SignedGatewayHttpSampleClient(clock=lambda: 150,
            public_resolver=PublicResolver(), transport=httpx.MockTransport(forward))
        received = await client.dispatch(request=fixture.request, check=fixture.check,
                                        destination=destination, credentials=credentials)
        self.assertEqual(received.code.value, "received")
        self.assertIsNotNone(received.result)
        self.assertEqual(received.result.request, fixture.request)
        self.assertEqual(dns_calls, ["gateway.example.invalid"])
        self.assertEqual(outer_calls, [True])
        selected = {}
        for distribution, expected in (
                ("control-plane-kit-core", "976901c609d950a557ec1e9966f018e8ff6e16aa"),
                ("control-plane-kit-server-sdk", "d61b374cb2a23d773c31748f47f88169499298b7")):
            coordinate = json.loads(metadata.distribution(distribution).read_text("direct_url.json"))
            self.assertIn(expected, coordinate["url"])
            selected[distribution] = expected
        print("Combined sample provenance: " + json.dumps(dict(sender_revision=revision,
            sender_file=str(source), selected=selected, public_dns="injected-public-answer",
            outer="ASGI injection after public address validation; Host/SNI asserted",
            child="configured HTTP origin asserted, ASGI injected real SDK",
            application="real numeric-loopback ready endpoint; credential-free",
            result=received.code.value, outer_calls=len(outer_calls)), sort_keys=True))
        return received.result

    async def test_wrong_pair_and_selector_make_zero_child_calls(self):
        fixture = Fixture(8081)
        calls = []
        def child(request):
            calls.append(True)
            return httpx.Response(500)
        app = self.relay(fixture, httpx.MockTransport(child))
        wrong = fixture.credential(request=replace(fixture.request, request_id="another-request"))
        cases = ((wrong, None, None, 403),
            (fixture.credential(), None, fixture.envelope(fixture.credential(), target_id="another-route"), 403),
            (fixture.credential(), fixture.credential(gateway=True,
                purpose=core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE), None, 401))
        for workload, token, envelope, status in cases:
            with self.subTest(status=status):
                response = await self.supplied_test_sender(app, fixture, workload, token=token, envelope=envelope)
                self.assertEqual(response.status_code, status)
                self.assertEqual(set(response.json()), {"code"})
        self.assertEqual(calls, [])

    async def test_mismatched_200_is_not_accepted_sample_evidence(self):
        fixture = Fixture(8081)
        other = replace(fixture.request, request_id="another-request")
        result = HttpVerificationSampleResult(other, VerificationOutcome.FAILED)
        raw = result.canonical_bytes(installed_check=fixture.check)
        calls = []
        def child(request):
            calls.append(True)
            return httpx.Response(200, content=raw, headers={"content-type": "application/json"})
        app = self.relay(fixture, httpx.MockTransport(child))
        response = await self.supplied_test_sender(app, fixture, fixture.credential())
        self.assertEqual(response.status_code, 200)
        with self.assertRaises(ValueError):
            HttpVerificationSampleResultCodec(fixture.request, fixture.check).decode_canonical_bytes(response.content)
        self.assertEqual(calls, [True])

    async def test_outer_failures_are_bounded_unavailability_without_retry(self):
        fixture = Fixture(8081)
        cases = (
            (302, b"peer-secret", {}, 502),
            (500, b"peer-secret", {}, 502),
            (200, b"x" * 2049, {"content-type": "application/json"}, 502),
            (200, b"peer-secret", {"content-type": "application/json", "content-encoding": "br"}, 502),
        )
        for status, body, headers, expected in cases:
            calls = []
            def child(request):
                calls.append(True)
                return httpx.Response(status, stream=httpx.ByteStream(body), headers=headers)
            with self.subTest(status=status, headers=headers):
                response = await self.supplied_test_sender(
                    self.relay(fixture, httpx.MockTransport(child)), fixture, fixture.credential())
                self.assertEqual(response.status_code, expected)
                self.assertEqual(response.json(), {"code": "gateway.http-sample.target-failure"})
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(calls, [True])
        calls = []
        def timeout(request):
            calls.append(True)
            raise httpx.ReadTimeout("peer-secret")
        response = await self.supplied_test_sender(
            self.relay(fixture, httpx.MockTransport(timeout)), fixture, fixture.credential())
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json(), {"code": "gateway.http-sample.timeout"})
        self.assertEqual(calls, [True])
