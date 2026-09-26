"""Explicit process-owned source support, separate from image qualification."""
from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import stat

from control_plane_kit_core.products import ProductDescriptorCodec, ProductDescriptorDocument
from control_plane_kit_operations.health_receiver_trust import HealthReceiverDecoders
from .health_receiver_adapters import health_receiver_decoders


PROFILE = "cpk-managed-health-source-support.v1"
MAX_SUPPORT_BYTES = 1_048_576
MAX_SUPPORT_PRODUCTS = 16
_ROLES = frozenset({"cpk-workload", "hello-workload", "gateway", "cloudflared-native-reader-v1"})
_INVALID = "managed health support is invalid"


class ManagedHealthSupportError(ValueError):
    """Fixed public startup refusal without candidate contents or paths."""


@dataclass(frozen=True, slots=True, repr=False)
class ManagedHealthProduct:
    role: str
    document: ProductDescriptorDocument

    def __post_init__(self):
        try:
            if (type(self.role) is not str or self.role not in _ROLES
                    or type(self.document) is not ProductDescriptorDocument
                    or ProductDescriptorCodec().decode_document(self.document.content) != self.document):
                raise ValueError
            return
        except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
            failure = ManagedHealthSupportError(_INVALID)
        raise failure


@dataclass(frozen=True, slots=True, repr=False)
class ManagedHealthSupport:
    """Immutable operator admission; API registration cannot populate this value."""
    products: tuple[ManagedHealthProduct, ...] = ()
    receiver_decoders: HealthReceiverDecoders = field(init=False, repr=False)

    def __post_init__(self):
        try:
            if type(self.products) is not tuple or len(self.products) > MAX_SUPPORT_PRODUCTS:
                raise ValueError
            identities = set()
            by_role = {role: [] for role in _ROLES}
            for item in self.products:
                if type(item) is not ManagedHealthProduct:
                    raise ValueError
                checked = replace(item)
                identity = checked.document.product.identity.key
                if identity in identities:
                    raise ValueError
                identities.add(identity)
                by_role[checked.role].append(checked.document)
            if len(by_role["cloudflared-native-reader-v1"]) > 1:
                raise ValueError
            registry = health_receiver_decoders(
                workload_documents=tuple(by_role["cpk-workload"]),
                hello_documents=tuple(by_role["hello-workload"]),
                gateway_documents=tuple(by_role["gateway"]),
                gateway_self_documents=tuple(by_role["gateway"]),
            )
            object.__setattr__(self, "receiver_decoders", registry)
            return
        except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
            failure = ManagedHealthSupportError(_INVALID)
        raise failure

    @property
    def native_reader_document(self) -> ProductDescriptorDocument | None:
        return next((item.document for item in self.products
                     if item.role == "cloudflared-native-reader-v1"), None)


def _closed(value, keys):
    if type(value) is not dict or set(value) != keys:
        raise ValueError
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _constant(_value):
    raise ValueError


def decode_managed_health_support(raw: bytes) -> ManagedHealthSupport:
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_SUPPORT_BYTES:
            raise ValueError
        value = _closed(json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                                  parse_constant=_constant), {"profile", "products"})
        if value["profile"] != PROFILE or type(value["products"]) is not list:
            raise ValueError
        if len(value["products"]) > MAX_SUPPORT_PRODUCTS:
            raise ValueError
        products = []
        for entry in value["products"]:
            entry = _closed(entry, {"role", "document"})
            if type(entry["document"]) is not dict:
                raise ValueError
            document = ProductDescriptorCodec().decode_document(
                json.dumps(entry["document"], allow_nan=False).encode("utf-8"))
            products.append(ManagedHealthProduct(entry["role"], document))
        return ManagedHealthSupport(tuple(products))
    except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        failure = ManagedHealthSupportError(_INVALID)
    raise failure


def read_managed_health_support(path: str | None) -> ManagedHealthSupport:
    if path is None:
        return ManagedHealthSupport()
    try:
        if (type(path) is not str or not 1 <= len(path) <= 4096
                or not Path(path).is_absolute()):
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            info = os.fstat(descriptor)
            # ConfigurationArtifact delivery is root-owned0444. Its public
            # policy bytes must be readable by the receiving numeric user.
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o444
                    or info.st_uid not in (0, os.geteuid()) or info.st_size > MAX_SUPPORT_BYTES):
                raise ValueError
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read(MAX_SUPPORT_BYTES + 1)
        finally:
            os.close(descriptor)
        return decode_managed_health_support(raw)
    except (OSError, ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        failure = ManagedHealthSupportError(_INVALID)
    raise failure
