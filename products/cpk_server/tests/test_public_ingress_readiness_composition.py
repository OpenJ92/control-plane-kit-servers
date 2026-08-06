from __future__ import annotations

from dataclasses import dataclass, field
import unittest

import httpx

from control_plane_kit_core.probe_intents import (
    EndpointContext,
    LiteralEndpointMaterial,
    RuntimeEndpointObservation,
)
from control_plane_kit_core.public_ingress import (
    IngressAuthorityReference,
    NamedPublicIngress,
    PublicIngressObservationStatus,
    PublicIngressTarget,
)
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import HttpCheck, VerificationPolicy
from control_plane_kit_servers_cpk_server.server import (
    BootstrapConfigurationError,
    _public_dns_resolver,
    _public_ingress_readiness_verifier,
)


@dataclass
class RecordingPublicResolver:
    addresses: tuple[str, ...]
    hostnames: list[str] = field(default_factory=list)

    def resolve(self, hostname: str) -> tuple[str, ...]:
        self.hostnames.append(hostname)
        return self.addresses


@dataclass(frozen=True)
class PublicDnsBootstrap:
    public_dns_resolver_endpoint: str


class PublicIngressReadinessCompositionTests(unittest.TestCase):
    def test_production_factory_injects_refreshable_redacted_resolver(self) -> None:
        endpoint = "https://1.1.1.1/dns-query"
        resolver = _public_dns_resolver(PublicDnsBootstrap(endpoint))
        verifier = _public_ingress_readiness_verifier(public_resolver=resolver)
        interpreter = verifier.interpreter_factory("gateway-001.openj92.dev")

        self.assertEqual(
            type(interpreter.public_resolver).__name__,
            "DnsOverHttpsPublicAddressResolver",
        )
        self.assertIs(interpreter.public_resolver, resolver)
        self.assertNotIn(endpoint, repr(resolver))
        self.assertNotIn("SystemPublicAddressResolver", repr(verifier))

    def test_malformed_resolver_bootstrap_is_bounded_and_redacted(self) -> None:
        endpoint = "https://user:credential@resolver.example/dns-query"

        with self.assertRaises(BootstrapConfigurationError) as raised:
            _public_dns_resolver(PublicDnsBootstrap(endpoint))

        self.assertEqual(
            str(raised.exception),
            "public DNS resolver bootstrap is malformed",
        )
        self.assertNotIn(endpoint, repr(raised.exception))

    def test_http_interpreter_ready_result_becomes_bounded_ingress_observation(
        self,
    ) -> None:
        resolver = RecordingPublicResolver(("1.1.1.1",))
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, content=b"ready")

        observation = _public_ingress_readiness_verifier(
            transport=httpx.MockTransport(handler),
            public_resolver=resolver,
        ).observe(
            ingress=_ingress(),
            check=_check(),
            endpoint=_endpoint(),
            attempt_timeout_seconds=5.0,
        )

        self.assertIs(observation.status, PublicIngressObservationStatus.READY)
        self.assertEqual(observation.url, "https://gateway-001.openj92.dev")
        self.assertEqual(resolver.hostnames, ["gateway-001.openj92.dev"])
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.host, "1.1.1.1")
        self.assertEqual(
            observation.evidence["verification_outcome"],
            "passed",
        )
        self.assertNotIn("1.1.1.1", repr(observation))

    def test_untrusted_public_address_is_unknown_and_performs_zero_http(self) -> None:
        resolver = RecordingPublicResolver(("127.0.0.1",))
        requests: list[httpx.Request] = []
        observation = _public_ingress_readiness_verifier(
            transport=httpx.MockTransport(
                lambda request: requests.append(request) or httpx.Response(200)
            ),
            public_resolver=resolver,
        ).observe(
            ingress=_ingress(),
            check=_check(),
            endpoint=_endpoint(),
            attempt_timeout_seconds=5.0,
        )

        self.assertIs(observation.status, PublicIngressObservationStatus.UNKNOWN)
        self.assertEqual(requests, [])
        self.assertEqual(
            observation.evidence["verification_outcome"],
            "rejected",
        )

    def test_non_ready_http_status_becomes_unready(self) -> None:
        observation = _public_ingress_readiness_verifier(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(503)
            ),
            public_resolver=RecordingPublicResolver(("1.1.1.1",)),
        ).observe(
            ingress=_ingress(),
            check=_check(),
            endpoint=_endpoint(),
            attempt_timeout_seconds=5.0,
        )

        self.assertIs(observation.status, PublicIngressObservationStatus.UNREADY)

    def test_operations_attempt_budget_bounds_one_http_observation(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(503)

        observation = _public_ingress_readiness_verifier(
            transport=httpx.MockTransport(handler),
            public_resolver=RecordingPublicResolver(("1.1.1.1",)),
        ).observe(
            ingress=_ingress(),
            check=HttpCheck(
                check_id="gateway-ready",
                provider_socket="control",
                path="/health/ready",
                policy=VerificationPolicy(
                    timeout_seconds=12.0,
                    maximum_attempts=3,
                ),
            ),
            endpoint=_endpoint(),
            attempt_timeout_seconds=2.0,
        )

        self.assertIs(observation.status, PublicIngressObservationStatus.UNREADY)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].extensions["timeout"]["read"], 2.0)


def _ingress() -> NamedPublicIngress:
    return NamedPublicIngress(
        ingress_id="gateway-public",
        authority_ref=IngressAuthorityReference("cloudflare-openj92"),
        target=PublicIngressTarget("gateway", "control"),
        connector_node_id="cloudflared",
        hostname="gateway-001.openj92.dev",
        readiness_check_id="ready",
    )


def _check() -> HttpCheck:
    return HttpCheck(
        check_id="gateway-ready",
        provider_socket="control",
        path="/health/ready",
    )


def _endpoint() -> RuntimeEndpointObservation:
    return RuntimeEndpointObservation(
        subject_id="gateway",
        socket_name="control",
        graph_id="graph-public",
        protocol=Protocol.HTTP,
        context=EndpointContext.PUBLIC,
        address=LiteralEndpointMaterial("https://gateway-001.openj92.dev:443"),
    )


if __name__ == "__main__":
    unittest.main()
