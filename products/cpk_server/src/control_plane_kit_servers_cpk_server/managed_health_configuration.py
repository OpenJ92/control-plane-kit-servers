"""Bounded, immutable process input; no provider contact or runtime authority."""
from dataclasses import dataclass
import json
import os
import stat

from control_plane_kit_core.products import (
    ProductDescriptorCodec, ProductDescriptorDocument, ProductReference,
)
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_interpreters.docker import DockerUnixSocketClientConfig
from control_plane_kit_interpreters.docker.connector_connection import DockerConnectorConnectionQualifier
from control_plane_kit_interpreters.docker.sdk import ConnectorConnectionProfile

from .health_receiver_adapters import health_receiver_decoders
from .managed_health_placement import DockerRuntimeClientSelector, DockerRuntimePolicyBinding


_INVALID = "managed health process configuration is invalid"
_MAX_BYTES = 1_048_576
_INPUT_ERRORS = (ValueError, TypeError, AttributeError, KeyError, OverflowError, RecursionError)


@dataclass(frozen=True, slots=True, repr=False)
class ManagedHealthProcessConfiguration:
    local_client_config: DockerUnixSocketClientConfig
    provider_clients: DockerRuntimeClientSelector
    gateway_documents: tuple[ProductDescriptorDocument, ...]
    native_product_document: ProductDescriptorDocument

    def __post_init__(self):
        try:
            if (type(self.local_client_config) is not DockerUnixSocketClientConfig
                    or type(self.provider_clients) is not DockerRuntimeClientSelector
                    or not 1 <= len(self.provider_clients.bindings) <= 64
                    or type(self.gateway_documents) is not tuple
                    or not 1 <= len(self.gateway_documents) <= 64):
                raise ValueError
            self.local_client_config.__post_init__()
            self.provider_clients.__post_init__()
            if any(type(binding) is not DockerRuntimePolicyBinding
                    or binding.local_client_config is not self.local_client_config
                    for binding in self.provider_clients.bindings):
                raise ValueError
            references = []
            for document in self.gateway_documents:
                _canonical_document(document)
                reference = ProductReference.from_document(document)
                if reference in references:
                    raise ValueError
                references.append(reference)
            health_receiver_decoders(gateway_documents=self.gateway_documents)
            _canonical_document(self.native_product_document)
            DockerConnectorConnectionQualifier(
                ProductReference.from_document(self.native_product_document),
                self.native_product_document.product.image.execution_reference,
                profile=ConnectorConnectionProfile.MANAGED_WRAPPER_V1,
            )
            return
        except _INPUT_ERRORS:
            pass
        # Do not retain the document, path or provider exception as context.
        raise ValueError(_INVALID)


def _canonical_document(document):
    if (type(document) is not ProductDescriptorDocument
            or type(document.content) is not bytes
            or ProductDescriptorCodec().decode_document(document.content) != document):
        raise ValueError


def _object(value, keys):
    if type(value) is not dict or value.keys() != keys:
        raise ValueError
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError


def _documents_text(value):
    if type(value) is not str:
        raise ValueError
    return ProductDescriptorCodec().decode_document(value.encode("utf-8"))


def decode_managed_health_process_configuration(raw: bytes) -> ManagedHealthProcessConfiguration:
    """Decode a closed schema using canonical document and policy owners."""
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_BYTES:
            raise ValueError
        value = _object(json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant),
            {"schema", "docker", "scopes", "gateway_documents", "native_product_document"})
        if value["schema"] != "cpk-server.managed-health.v1":
            raise ValueError
        docker = _object(value["docker"], {"socket_path", "request_timeout"})
        policy = DockerUnixSocketClientConfig(docker["socket_path"], docker["request_timeout"])
        for items in (value["scopes"], value["gateway_documents"]):
            if type(items) is not list or not 1 <= len(items) <= 64:
                raise ValueError
        bindings = []
        for scope in value["scopes"]:
            _object(scope, {"workspace_id", "runtime_id", "authority_ref"})
            bindings.append(DockerRuntimePolicyBinding(scope["workspace_id"], scope["runtime_id"],
                RuntimeAuthorityReference(scope["authority_ref"]), policy))
        return ManagedHealthProcessConfiguration(policy, DockerRuntimeClientSelector(tuple(bindings)),
            tuple(_documents_text(document) for document in value["gateway_documents"]),
            _documents_text(value["native_product_document"]))
    except _INPUT_ERRORS:
        pass
    raise ValueError(_INVALID)


def read_managed_health_process_configuration(path: str) -> ManagedHealthProcessConfiguration:
    """Read once from a regular file. Ancestor directories must be trusted."""
    try:
        if (type(path) is not str or not 1 <= len(path.encode("utf-8")) <= 4096
                or not os.path.isabs(path)
                or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in path)):
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= _MAX_BYTES:
                raise ValueError
            content = bytearray()
            while len(content) <= _MAX_BYTES:
                chunk = os.read(descriptor, min(65_536, _MAX_BYTES + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
            return decode_managed_health_process_configuration(bytes(content))
        finally:
            os.close(descriptor)
    except (*_INPUT_ERRORS, OSError):
        pass
    raise ValueError(_INVALID)
