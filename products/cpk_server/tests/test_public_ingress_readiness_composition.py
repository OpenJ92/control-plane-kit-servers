from __future__ import annotations

from dataclasses import dataclass
import unittest

from control_plane_kit_servers_cpk_server.server import (
    BootstrapConfigurationError,
    _public_dns_resolver,
)


@dataclass(frozen=True)
class PublicDnsBootstrap:
    public_dns_resolver_endpoint: str


class PublicDnsResolverCompositionTests(unittest.TestCase):
    def test_public_dns_factory_constructs_refreshable_redacted_resolver(self) -> None:
        endpoint = "https://1.1.1.1/dns-query"
        resolver = _public_dns_resolver(PublicDnsBootstrap(endpoint))

        self.assertEqual(
            type(resolver).__name__,
            "DnsOverHttpsPublicAddressResolver",
        )
        self.assertNotIn(endpoint, repr(resolver))

    def test_public_dns_factory_rejects_malformed_endpoint_with_bounded_error(
        self,
    ) -> None:
        endpoint = "https://user:credential@resolver.example/dns-query"

        with self.assertRaises(BootstrapConfigurationError) as raised:
            _public_dns_resolver(PublicDnsBootstrap(endpoint))

        self.assertEqual(
            str(raised.exception),
            "public DNS resolver bootstrap is malformed",
        )
        self.assertNotIn(endpoint, repr(raised.exception))


if __name__ == "__main__":
    unittest.main()
