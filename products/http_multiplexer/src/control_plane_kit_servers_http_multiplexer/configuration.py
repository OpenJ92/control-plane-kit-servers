"""Multiplexer's public, integrity-sensitive configuration and source contract."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping
from urllib import parse

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket, RequirementSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType, ConfigurationFileMode
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import ProductRuntimeContract, ProviderRuntimePort
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import VerificationContract, VerificationPolicy, HttpCheck
from control_plane_kit_core.receiver_configuration import (
    ReceiverNodeControlConfiguration, ReceiverNodeControlConfigurationCodec,
)
from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT

CONTROL_PATH = "/etc/cpk/multiplexer/control.json"
MAX_CONTROL_BYTES = 65_536


class MultiplexerConfigurationError(ValueError):
    """Malformed Multiplexer startup configuration; never carries source material."""


def multiplexer_control_declaration() -> core.WorkloadNodeControlSurfaceDeclaration:
    return core.WorkloadNodeControlSurfaceDeclaration(
        core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "internal"),
            (), health_reads=(core.NodeHealthReadKind.LIVENESS,),
        ), profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
    )


def _require_multiplexer_configuration(configuration: ReceiverNodeControlConfiguration) -> ReceiverNodeControlConfiguration:
    if (type(configuration) is not ReceiverNodeControlConfiguration
            or configuration.declaration != multiplexer_control_declaration()):
        raise ValueError
    return configuration


def decode_multiplexer_control_configuration(raw: bytes) -> ReceiverNodeControlConfiguration:
    """Decode common receiving values and enforce this product's declaration."""
    try:
        return _require_multiplexer_configuration(ReceiverNodeControlConfigurationCodec().decode_bytes(raw))
    except Exception:
        failure = MultiplexerConfigurationError("Multiplexer control configuration is invalid")
    raise failure


def read_multiplexer_control_configuration() -> ReceiverNodeControlConfiguration:
    try:
        from control_plane_kit_server_sdk.wrapper import load_wrapper_configuration
        return _require_multiplexer_configuration(load_wrapper_configuration())
    except Exception:
        failure = MultiplexerConfigurationError("Multiplexer control configuration is invalid")
    raise failure


def multiplexer_control_configuration_artifact(config: ReceiverNodeControlConfiguration) -> ConfigurationArtifact:
    try:
        content = ReceiverNodeControlConfigurationCodec().encode_bytes(config)
        decode_multiplexer_control_configuration(content)
        return ConfigurationArtifact("multiplexer-control", CONTROL_PATH, ConfigurationMediaType.JSON,
                                     content.decode("utf-8"), ConfigurationFileMode.READ_ONLY)
    except Exception:
        failure = MultiplexerConfigurationError("Multiplexer control configuration is invalid")
    raise failure


def multiplexer_source_runtime_contract(artifact: ConfigurationArtifact) -> ProductRuntimeContract:
    """Source-only contract; does not replace the historical published descriptor."""
    try:
        if (type(artifact) is not ConfigurationArtifact or artifact.artifact_id != "multiplexer-control"
                or artifact.target_path != CONTROL_PATH or artifact.media_type is not ConfigurationMediaType.JSON
                or artifact.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        decode_multiplexer_control_configuration(artifact.content.encode("utf-8"))
        return ProductRuntimeContract(
            sockets=BlockSockets(
                requirements=(
                    RequirementSocket("primary", Protocol.HTTP, ("MULTIPLEXER_PRIMARY_URL",)),
                    RequirementSocket("observer-a", Protocol.HTTP, ("MULTIPLEXER_OBSERVER_A_URL",), required=False),
                    RequirementSocket("observer-b", Protocol.HTTP, ("MULTIPLEXER_OBSERVER_B_URL",), required=False),
                ),
                providers=(ProviderSocket("internal", Protocol.HTTP),)),
            provider_ports=(ProviderRuntimePort("internal", 8000),),
            configuration_artifacts=(artifact,),
            public_environment=(PublicStaticEnvironmentBinding(WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT, CONTROL_PATH),),
            capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(multiplexer_control_declaration().surface,),
            verification=VerificationContract(checks=(
                HttpCheck(check_id="live", provider_socket="internal", path="/health/live",
                          policy=VerificationPolicy(maximum_attempts=5)),
            )),
        )
    except Exception:
        failure = MultiplexerConfigurationError("Multiplexer control configuration is invalid")
    raise failure


OBSERVER_ENVIRONMENTS = ("MULTIPLEXER_OBSERVER_A_URL", "MULTIPLEXER_OBSERVER_B_URL")


@dataclass(frozen=True, slots=True, repr=False)
class MultiplexerSettings:
    """Startup primary and observer values; no observer delivery state."""

    primary_url: str
    observer_urls: tuple[str, ...] = ()
    port: int = 8000

    def __post_init__(self) -> None:
        accepted = False
        try:
            accepted = (
                type(self.primary_url) is str and _valid_url(self.primary_url)
                and type(self.observer_urls) is tuple
                and all(type(value) is str and _valid_url(value) for value in self.observer_urls)
                and type(self.port) is int and 0 < self.port < 65536
            )
        except Exception:
            accepted = False
        if not accepted:
            raise MultiplexerConfigurationError("MULTIPLEXER_PRIMARY_URL, observer URL or PORT is invalid")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "MultiplexerSettings":
        try:
            values = os.environ if environment is None else environment
            primary_url = values.get("MULTIPLEXER_PRIMARY_URL", "").strip().rstrip("/")
            observers = tuple(
                values.get(name, "").strip().rstrip("/")
                for name in OBSERVER_ENVIRONMENTS if values.get(name, "").strip()
            )
            return cls(primary_url, observers, int(values.get("PORT", "8000")))
        except Exception:
            failure = MultiplexerConfigurationError("MULTIPLEXER_PRIMARY_URL, observer URL or PORT is invalid")
        raise failure


def _valid_url(value: str) -> bool:
    parsed = parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
