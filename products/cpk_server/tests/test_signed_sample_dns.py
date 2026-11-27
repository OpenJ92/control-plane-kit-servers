"""Exercise the installed sender wiring with synthetic authority and bounded network substitutes."""
import asyncio
from dataclasses import replace
from pathlib import Path
from threading import Event, get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import dns.message
import dns.rdatatype
import dns.rrset
import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import control_plane_kit_core as core
from control_plane_kit_core.http_verification_samples import HttpVerificationSampleGrant, HttpVerificationSampleResult
from control_plane_kit_core.postgres_readiness import PostgresReadinessObserver
from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from control_plane_kit_core.receiver_management_routes import ReceiverManagementRouteBinding
from control_plane_kit_core.verification import HttpVerificationEvidence, VerificationOutcome
from control_plane_kit_interpreters.probes.http_sample_transport import SelectedHttpSampleGateway, SignedHttpSampleCredentials
from control_plane_kit_operations.http_sample_execution import HttpSampleExecutionSupport
from control_plane_kit_operations.managed_verification_execution import ManagedVerificationExecutionSupport
from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import gateway_http_sample_declared_runtime_contract
from control_plane_kit_servers_cpk_server import control_configuration, server
from control_plane_kit_servers_cpk_server.health_receiver_adapters import health_receiver_decoders
from control_plane_kit_servers_cpk_server.http_sample_composition import gateway_http_sample_binding
from cpk_http_host_fixtures import fixture
from scripts.http_sample_fixture import SampleAuthority


PRODUCTS = Path(__file__).resolve().parents[2]


def managed_support():
    codec = ProductDescriptorCodec()
    gateway = codec.decode_document((PRODUCTS / 'cpk_local_gateway/product.cpk.json').read_bytes())
    gateway = codec.encode_document(replace(gateway.product, runtime_contract=gateway_http_sample_declared_runtime_contract()))
    postgres = codec.decode_document((PRODUCTS / 'postgres_server/product.cpk.json').read_bytes())
    observer = PostgresReadinessObserver(ProductReference.from_document(postgres), postgres.product.image,
        'postgres', 'cpk', 'cpk', '/run/secrets/password', 'POSTGRES_PASSWORD_FILE')
    return ManagedVerificationExecutionSupport(HttpSampleExecutionSupport(gateway_http_sample_binding(gateway), 'control'),
        (observer,), health_receiver_decoders(gateway_documents=(gateway,)))


def signed_sample():
    control = fixture().config
    contract = control_configuration.cpk_source_runtime_contract(control_configuration.CpkSourceVariant.CPK,
        control_configuration.cpk_control_configuration_artifact(control))
    authority = SampleAuthority(control, contract)
    request = authority.request()
    gateway = request.gateway_target
    ingress = core.NamedPublicIngress('management', core.IngressAuthorityReference('fixture-zone'),
        core.PublicIngressTarget(gateway.node_id.value, 'control'), 'connector', 'gateway.example.invalid')
    route = ReceiverManagementRouteBinding(request.route_id, request.target, control.declaration, 'http://child:8080')
    destination = SelectedHttpSampleGateway(ingress, gateway, route, 'control')
    workload = HttpVerificationSampleGrant(request=request, purpose=core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE,
        issuer='source-sample-witness', key_id='source-sample', audience=core.receiver_node_control_audience(request.target),
        issued_at=100, not_before=100, expires_at=115, jti='workload-request')
    transit = replace(workload, purpose=core.DelegationKeyPurpose.GATEWAY_HTTP_VERIFICATION_SAMPLE_TRANSIT,
        issuer='gateway-issuer', key_id='transit-key', jti='transit-request',
        audience=f'gateway:{gateway.workspace_id.value}:{gateway.node_id.value}')
    def sign(grant, key, typ, claim):
        claims = dict(iss=grant.issuer, aud=grant.audience, iat=grant.issued_at, nbf=grant.not_before,
            exp=grant.expires_at, jti=grant.jti, **{claim: grant.descriptor()})
        return jwt.encode(claims, key, algorithm='EdDSA', headers={'kid': grant.key_id, 'typ': typ}).encode('ascii')
    credentials = SignedHttpSampleCredentials(
        sign(transit, Ed25519PrivateKey.generate(), 'CPK-GATEWAY-HTTP-VERIFICATION-SAMPLE-TRANSIT+JWT',
             'gateway_http_verification_sample_transit'),
        sign(workload, authority.private, 'CPK-WORKLOAD-HTTP-VERIFICATION-SAMPLE+JWT', 'workload_http_verification_sample'),
        transit, workload)
    return dict(request=request, check=authority.check, destination=destination, credentials=credentials)


class SignedSampleDnsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.support = managed_support()
        self.inputs = signed_sample()
        self.calls = []
        self.dns_threads = []

    def client(self, dns_handler, *, combined=False):
        config = SimpleNamespace(public_dns_resolver_endpoint='https://resolver.example.invalid/dns-query',
            http_sample_support=self.support.http_samples, managed_verification_support=self.support if combined else None)
        resolver = server._public_dns_resolver(config, transport=httpx.MockTransport(dns_handler))
        with patch.object(server, '_public_dns_resolver', return_value=resolver), \
                patch('control_plane_kit_interpreters.docker.DockerSdkClient.from_authority'):
            adapter = server._docker_runtime_interpreter(config, SimpleNamespace(authorized_resolver=Mock()))
        async def relay(request):
            self.calls.append(request)
            result = HttpVerificationSampleResult(self.inputs['request'], VerificationOutcome.PASSED, HttpVerificationEvidence(200, 1))
            return httpx.Response(200, headers={'Content-Type': 'application/json'},
                content=result.canonical_bytes(installed_check=self.inputs['check']))
        return replace(adapter.http_sample_executor.client, clock=lambda: 101, transport=httpx.MockTransport(relay))

    def dns_response(self, request, address):
        self.dns_threads.append(get_ident())
        query = dns.message.from_wire(request.content)
        question, = query.question
        response = dns.message.make_response(query)
        if question.rdtype == dns.rdatatype.A:
            response.answer.append(dns.rrset.from_text(question.name, 30, 'IN', 'A', address))
        return httpx.Response(200, headers={'Content-Type': 'application/dns-message'}, content=response.to_wire())

    async def test_both_compositions_dispatch_after_off_loop_resolution(self):
        loop_thread = get_ident()
        for combined in (False, True):
            with self.subTest(combined=combined):
                self.calls.clear()
                self.dns_threads.clear()
                client = self.client(lambda request: self.dns_response(request, '8.8.8.8'), combined=combined)
                result = await client.dispatch(**self.inputs)
                self.assertEqual(result.code.value, 'received')
                self.assertEqual(result.result.request, self.inputs['request'])
                self.assertIs(result.result.outcome, VerificationOutcome.PASSED)
                self.assertEqual(len(self.dns_threads), 2)
                self.assertNotIn(loop_thread, self.dns_threads)
                outbound, = self.calls
                self.assertEqual(str(outbound.url), 'https://8.8.8.8/cpk/verification/http')
                self.assertEqual(outbound.headers['Host'], 'gateway.example.invalid:443')

    async def test_failed_or_disallowed_answers_never_reach_gateway(self):
        for resolver in (lambda request: httpx.Response(503), lambda request: self.dns_response(request, '127.0.0.1')):
            with self.subTest(resolver=resolver):
                result = await self.client(resolver).dispatch(**self.inputs)
                self.assertIsNone(result.result)
                self.assertEqual(self.calls, [])

    async def test_expired_dns_wait_cannot_dispatch_when_resolution_later_finishes(self):
        release, finished = Event(), Event()
        def slow_dns(request):
            release.wait(1)
            response = self.dns_response(request, '8.8.8.8')
            if len(self.dns_threads) == 2:
                finished.set()
            return response
        client = replace(self.client(slow_dns), timeout_seconds=0.08)
        try:
            result = await client.dispatch(**self.inputs)
            self.assertEqual(result.code.value, 'timed-out')
            self.assertIsNone(result.result)
        finally:
            release.set()
        self.assertTrue(await asyncio.to_thread(finished.wait, 2))
        self.assertEqual(self.calls, [])
