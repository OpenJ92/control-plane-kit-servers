from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from control_plane_kit_operations import (
    CloudflareZoneIngressAuthority,
    IngressResourcePresence,
    IngressReservationObservation,
    IngressTunnelObservation,
    RetainedIngressDeactivationResult,
)


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"


class FakePresence(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"


@dataclass(frozen=True)
class FakeReservation:
    dns_record_id: str
    hostname: str
    expected_tunnel_id: str


@dataclass(frozen=True)
class FakeResources:
    tunnel_id: str
    dns_record_id: str
    tunnel_name: str
    hostname: str


@dataclass(frozen=True)
class FakeReservationObservation:
    dns_record_id: str
    hostname: str
    presence: FakePresence
    tunnel_id: str | None = None


@dataclass(frozen=True)
class FakeTunnelObservation:
    tunnel_id: str
    presence: FakePresence


@dataclass(frozen=True)
class FakeDeactivation:
    reservation: FakeReservationObservation
    tunnel: FakeTunnelObservation


class RecordingCloudflareInterpreter:
    instance = None

    def __init__(self, **kwargs) -> None:
        self.bootstrap = kwargs
        self.calls = []
        type(self).instance = self

    def rebind(self, ingress, **kwargs):
        self.calls.append(("rebind", ingress, kwargs))
        return SimpleNamespace(
            tunnel_id="tunnel-new",
            tunnel_name="allocation-new",
            secret_custody_receipt=object(),
            dns_record_id="dns-record-1",
            hostname="gateway.openj92.dev",
            endpoint_url="https://gateway.openj92.dev",
        )

    def deactivate_preserving_reservation(self, **kwargs):
        self.calls.append(("deactivate", None, kwargs))
        return FakeDeactivation(
            FakeReservationObservation(
                "dns-record-1",
                "gateway.openj92.dev",
                FakePresence.PRESENT,
                "tunnel-old",
            ),
            FakeTunnelObservation("tunnel-old", FakePresence.ABSENT),
        )

    def release_reservation(self, **kwargs):
        self.calls.append(("release", None, kwargs))
        return FakeReservationObservation(
            "dns-record-1",
            "gateway.openj92.dev",
            FakePresence.ABSENT,
        )


class FakeZoneAuthority:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


def _fake_cloudflare_module() -> ModuleType:
    module = ModuleType("control_plane_kit_interpreters.cloudflare")
    module.CloudflareNamedIngressInterpreter = RecordingCloudflareInterpreter
    module.CloudflareOwnedHostnameReservation = FakeReservation
    module.CloudflareOwnedIngressResources = FakeResources
    module.CloudflareResourcePresence = FakePresence
    module.CloudflareZoneAuthority = FakeZoneAuthority
    return module


class RetainedIngressCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(PRODUCT_SRC))

    def tearDown(self) -> None:
        sys.path.remove(str(PRODUCT_SRC))
        RecordingCloudflareInterpreter.instance = None
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith(
                "control_plane_kit_servers_cpk_server."
            ):
                sys.modules.pop(name, None)

    def test_operations_does_not_import_interpreter_package(self) -> None:
        import control_plane_kit_operations  # noqa: F401

        self.assertFalse(
            any(
                name == "control_plane_kit_interpreters"
                or name.startswith("control_plane_kit_interpreters.")
                for name in sys.modules
            )
        )

    def test_rebind_translates_exact_reservation_coordinates(self) -> None:
        provider = self._provider()
        ingress = object()
        reservation = _reservation()
        authority = _authority()
        resolution_grant = object()
        custody_grant = object()

        result = provider.rebind(
            ingress,
            authority=authority,
            reservation=reservation,
            allocation_name="allocation-new",
            origin_service_url="http://gateway:8000",
            secret_resolution_grant=resolution_grant,
            secret_custody_grant=custody_grant,
        )

        self.assertEqual(result.tunnel_id, "tunnel-new")
        inner = RecordingCloudflareInterpreter.instance
        self.assertIsNotNone(inner)
        name, actual_ingress, kwargs = inner.calls[-1]
        self.assertEqual(name, "rebind")
        self.assertIs(actual_ingress, ingress)
        self.assertIsInstance(kwargs["authority"], FakeZoneAuthority)
        self.assertIsInstance(kwargs["reservation"], FakeReservation)
        self.assertEqual(
            kwargs["reservation"],
            FakeReservation(
                reservation.dns_record_id,
                reservation.hostname,
                reservation.expected_tunnel_id,
            ),
        )
        self.assertIs(kwargs["secret_resolution_grant"], resolution_grant)
        self.assertIs(kwargs["secret_custody_grant"], custody_grant)

    def test_deactivation_translates_exact_inputs_and_closed_results(self) -> None:
        provider = self._provider()
        reservation = _reservation()
        resources = _resources()

        result = provider.deactivate_preserving_reservation(
            authority=_authority(),
            reservation=reservation,
            resources=resources,
            secret_resolution_grant=object(),
            secret_custody_grant=object(),
        )

        self.assertIsInstance(result, RetainedIngressDeactivationResult)
        self.assertIsInstance(result.reservation, IngressReservationObservation)
        self.assertIs(result.reservation.presence, IngressResourcePresence.PRESENT)
        self.assertEqual(result.reservation.tunnel_id, "tunnel-old")
        self.assertIsInstance(result.tunnel, IngressTunnelObservation)
        self.assertIs(result.tunnel.presence, IngressResourcePresence.ABSENT)
        _, _, kwargs = RecordingCloudflareInterpreter.instance.calls[-1]
        self.assertEqual(
            kwargs["reservation"],
            FakeReservation(
                reservation.dns_record_id,
                reservation.hostname,
                reservation.expected_tunnel_id,
            ),
        )
        self.assertEqual(
            kwargs["resources"],
            FakeResources(
                resources.tunnel_id,
                resources.dns_record_id,
                resources.tunnel_name,
                resources.hostname,
            ),
        )

    def test_release_translates_exact_input_and_absence_result(self) -> None:
        provider = self._provider()
        reservation = _reservation()

        result = provider.release_reservation(
            authority=_authority(),
            reservation=reservation,
            secret_resolution_grant=object(),
        )

        self.assertIsInstance(result, IngressReservationObservation)
        self.assertIs(result.presence, IngressResourcePresence.ABSENT)
        self.assertIsNone(result.tunnel_id)
        _, _, kwargs = RecordingCloudflareInterpreter.instance.calls[-1]
        self.assertEqual(
            kwargs["reservation"],
            FakeReservation(
                reservation.dns_record_id,
                reservation.hostname,
                reservation.expected_tunnel_id,
            ),
        )

    def test_wrapper_repr_is_bounded_and_redacted(self) -> None:
        provider = self._provider()

        self.assertEqual(repr(provider), "CloudflareIngressProvider(<redacted>)")
        self.assertNotIn("secret://cloudflare/api-token", repr(provider))
        self.assertNotIn("provider-token", repr(provider))

    def test_disabled_ingress_bootstrap_constructs_no_provider(self) -> None:
        from control_plane_kit_servers_cpk_server.server import (
            IngressInterpreterBootstrapConfiguration,
            _ingress_interpreters,
        )

        config = SimpleNamespace(
            ingress_interpreters=IngressInterpreterBootstrapConfiguration()
        )

        self.assertEqual(_ingress_interpreters(config, _secret_provider()), {})

    def _provider(self):
        from control_plane_kit_servers_cpk_server.server import (
            _cloudflare_ingress_interpreter,
        )

        with patch.dict(
            sys.modules,
            {"control_plane_kit_interpreters.cloudflare": _fake_cloudflare_module()},
        ):
            return _cloudflare_ingress_interpreter(object(), _secret_provider())


def _secret_provider():
    return SimpleNamespace(
        authorized_resolver=SimpleNamespace(token="provider-token"),
        secret_custodian=SimpleNamespace(
            reference="secret://cloudflare/api-token"
        ),
    )


def _authority() -> CloudflareZoneIngressAuthority:
    return SimpleNamespace(
        account_id="account-1",
        zone_id="zone-1",
        zone_name="openj92.dev",
        api_token_ref="secret://cloudflare/api-token",
        allowed_hostname_pattern="*.openj92.dev",
    )


def _reservation():
    return SimpleNamespace(
        dns_record_id="dns-record-1",
        hostname="gateway.openj92.dev",
        expected_tunnel_id="tunnel-old",
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
