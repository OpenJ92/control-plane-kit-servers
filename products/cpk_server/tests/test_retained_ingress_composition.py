from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
import importlib
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"


@dataclass(frozen=True)
class FakeResources:
    tunnel_id: str
    dns_record_id: str
    tunnel_name: str
    hostname: str


class RecordingCloudflareInterpreter:
    instance = None

    def __init__(self, **kwargs) -> None:
        self.bootstrap = kwargs
        self.calls = []
        type(self).instance = self

    def create(self, ingress, **kwargs):
        self.calls.append(("create", ingress, kwargs))
        return SimpleNamespace(
            tunnel_id="tunnel-new",
            dns_record_id="dns-record-1",
            hostname="gateway.openj92.dev",
        )

    def teardown(self, **kwargs):
        self.calls.append(("teardown", None, kwargs))


class FakeZoneAuthority:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


def _fake_cloudflare_module() -> ModuleType:
    module = ModuleType("control_plane_kit_interpreters.cloudflare")
    module.CloudflareNamedIngressInterpreter = RecordingCloudflareInterpreter
    module.CloudflareOwnedIngressResources = FakeResources
    module.CloudflareZoneAuthority = FakeZoneAuthority
    return module


class CurrentIngressCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(PRODUCT_SRC))

    def tearDown(self) -> None:
        sys.path.remove(str(PRODUCT_SRC))
        RecordingCloudflareInterpreter.instance = None
        for name in tuple(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith(
                "control_plane_kit_servers_cpk_server."
            ):
                sys.modules.pop(name, None)

    def test_create_preserves_current_authority_and_secret_grants(self) -> None:
        provider = self._provider()
        ingress = object()
        resolution_grant = object()
        custody_grant = object()

        result = provider.create(
            ingress,
            authority=_authority(),
            allocation_name="allocation-new",
            origin_service_url="http://gateway:8000",
            secret_resolution_grant=resolution_grant,
            secret_custody_grant=custody_grant,
        )

        self.assertEqual(result.tunnel_id, "tunnel-new")
        name, actual_ingress, kwargs = RecordingCloudflareInterpreter.instance.calls[-1]
        self.assertEqual(name, "create")
        self.assertIs(actual_ingress, ingress)
        self.assertIsInstance(kwargs["authority"], FakeZoneAuthority)
        self.assertEqual(
            kwargs["authority"].__dict__,
            {
                "account_id": "account-1",
                "zone_id": "zone-1",
                "zone_name": "openj92.dev",
                "api_token_ref": "secret://cloudflare/api-token",
                "allowed_hostname_pattern": "*.openj92.dev",
            },
        )
        self.assertIs(kwargs["secret_resolution_grant"], resolution_grant)
        self.assertIs(kwargs["secret_custody_grant"], custody_grant)

    def test_teardown_preserves_current_resource_and_secret_grants(self) -> None:
        provider = self._provider()
        resolution_grant = object()
        custody_grant = object()

        provider.teardown(
            authority=_authority(),
            resources=_resources(),
            secret_resolution_grant=resolution_grant,
            secret_custody_grant=custody_grant,
        )

        name, _, kwargs = RecordingCloudflareInterpreter.instance.calls[-1]
        self.assertEqual(name, "teardown")
        self.assertIsInstance(kwargs["authority"], FakeZoneAuthority)
        self.assertEqual(kwargs["authority"].zone_id, "zone-1")
        self.assertEqual(
            kwargs["resources"],
            FakeResources(
                "tunnel-old",
                "dns-record-1",
                "allocation-old",
                "gateway.openj92.dev",
            ),
        )
        self.assertIs(kwargs["secret_resolution_grant"], resolution_grant)
        self.assertIs(kwargs["secret_custody_grant"], custody_grant)

    def test_wrapper_surface_is_current_only_and_redacted(self) -> None:
        provider = self._provider()

        self.assertEqual(repr(provider), "CloudflareIngressProvider(<redacted>)")
        self.assertEqual(
            {name for name in ("create", "teardown") if callable(getattr(provider, name, None))},
            {"create", "teardown"},
        )
        for retired in (
            "rebind",
            "deactivate_preserving_reservation",
            "release_reservation",
        ):
            self.assertFalse(hasattr(provider, retired))
        self.assertNotIn("secret://cloudflare/api-token", repr(provider))
        self.assertNotIn("provider-token", repr(provider))

    def test_disabled_ingress_bootstrap_constructs_no_provider(self) -> None:
        server = self._server()
        config = SimpleNamespace(
            ingress_interpreters=server.IngressInterpreterBootstrapConfiguration()
        )

        self.assertEqual(server._ingress_interpreters(config, _secret_provider()), {})

    def _server(self):
        try:
            return importlib.import_module(
                "control_plane_kit_servers_cpk_server.server"
            )
        except ImportError as error:
            self.fail(f"cpk-server cannot import accepted packages: {error}")

    def _provider(self):
        server = self._server()
        with patch.dict(
            sys.modules,
            {"control_plane_kit_interpreters.cloudflare": _fake_cloudflare_module()},
        ):
            return server._cloudflare_ingress_interpreter(
                object(), _secret_provider()
            )


def _secret_provider():
    return SimpleNamespace(
        authorized_resolver=SimpleNamespace(token="provider-token"),
        secret_custodian=SimpleNamespace(
            reference="secret://cloudflare/api-token"
        ),
    )


def _authority():
    return SimpleNamespace(
        account_id="account-1",
        zone_id="zone-1",
        zone_name="openj92.dev",
        api_token_ref="secret://cloudflare/api-token",
        allowed_hostname_pattern="*.openj92.dev",
    )


def _resources():
    return SimpleNamespace(
        tunnel_id="tunnel-old",
        dns_record_id="dns-record-1",
        tunnel_name="allocation-old",
        hostname="gateway.openj92.dev",
    )


if __name__ == "__main__":
    unittest.main()
