"""Explicit public sender expectations, never product or execution qualification.

Imported only by the opted-in source grandparent. Trusted ancestor directories
and approved exact artifact inputs are the bootstrap owner's responsibility.
Registration, permission, version selection and provider truth remain external.
"""
import json
import os
import stat

from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference, ProductReferenceCodec
from control_plane_kit_core.postgres_readiness import PostgresReadinessObserver
from control_plane_kit_core.secrets import SecretFileDelivery, SecretUseIntent
from control_plane_kit_core.verification import PostgresQueryCheck
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_operations.http_sample_execution import HttpSampleExecutionSupport
from control_plane_kit_operations.managed_verification_execution import ManagedVerificationExecutionSupport
from .health_receiver_adapters import health_receiver_decoders
from .http_sample_composition import gateway_http_sample_binding

_MAX_BYTES = 1_048_576


def _require(value):
    if value is not True:
        raise ValueError("managed verification process configuration is invalid")


def _unique(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value)
        value[key] = item
    return value


def _invalid_constant(_):
    raise ValueError("managed verification process configuration is invalid")


def decode_managed_verification_configuration(raw, config):
    """Construct one support from the exact frozen installation variant docs.

    No installed product, private signer or future run receipt is inferred.
    Operations independently matches these expectations to actual registration.
    """
    _require(type(raw) is bytes and 1 <= len(raw) <= _MAX_BYTES
        and config.workspace_authority is not None and config.runtime_dispatcher.enabled
        and config.runtime_dispatcher.runtime_kinds == (RuntimeKind.DOCKER,)
        and config.managed_health_process is not None
        and config.managed_health_process.provider_clients is None)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
        parse_constant=_invalid_constant)
    _require(type(value) is dict and value.keys() == {
        "schema", "gateway_product", "postgres_product_document"}
        and value["schema"] == "cpk-server.managed-verification.v1"
        and type(value["postgres_product_document"]) is str)
    reference = ProductReferenceCodec().decode(value["gateway_product"])
    gateways = tuple(document for document in config.managed_health_process.gateway_documents
        if ProductReference.from_document(document) == reference)
    _require(len(gateways) == 1)
    gateway, = gateways
    document = ProductDescriptorCodec().decode_document(value["postgres_product_document"].encode("utf-8"))
    contract = document.product.runtime_contract
    _require(len(contract.verification.checks) == 1)
    check, = contract.verification.checks
    _require(type(check) is PostgresQueryCheck and check.authentication is not None)
    deliveries = tuple(item for item in contract.secret_deliveries
        if type(item) is SecretFileDelivery and item.intent is SecretUseIntent.POSTGRES_PASSWORD
        and item.reference == check.authentication.password_reference)
    _require(len(deliveries) == 1 and deliveries[0].path_binding is not None
        and tuple(port.container_port for port in contract.provider_ports
            if port.provider_socket == check.provider_socket) == (5432,))
    delivery, = deliveries
    observer = PostgresReadinessObserver(ProductReference.from_document(document), document.product.image,
        check.provider_socket, check.authentication.database, check.authentication.username,
        delivery.target_path, delivery.path_binding.environment_name)
    transit = gateway.product.runtime_contract.gateway_transit
    _require(transit is not None)
    samples = HttpSampleExecutionSupport(gateway_http_sample_binding(gateway), transit.provider_socket_name)
    return ManagedVerificationExecutionSupport(samples, (observer,),
        health_receiver_decoders(gateway_documents=(gateway,)))


def read_managed_verification_configuration(path, config):
    """Read one bounded regular public file, refusing symlink/special targets."""
    _require(type(path) is str and 1 <= len(path.encode("utf-8")) <= 4096
        and os.path.isabs(path)
        and not any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in path))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        metadata = os.fstat(descriptor)
        _require(stat.S_ISREG(metadata.st_mode) and 1 <= metadata.st_size <= _MAX_BYTES)
        content = bytearray()
        while len(content) <= _MAX_BYTES:
            chunk = os.read(descriptor, min(65_536, _MAX_BYTES + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        _require(1 <= len(content) <= _MAX_BYTES)
    finally:
        os.close(descriptor)
    return decode_managed_verification_configuration(bytes(content), config)
