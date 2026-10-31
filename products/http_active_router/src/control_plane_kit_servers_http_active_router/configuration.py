"""Router's public, integrity-sensitive configuration and source contract."""
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

CONTROL_PATH = "/etc/cpk/router/control.json"
MAX_CONTROL_BYTES = 65_536


class RouterConfigurationError(ValueError):
    """Malformed Router startup configuration; never carries source material."""


def router_control_declaration() -> core.WorkloadNodeControlSurfaceDeclaration:
    return core.WorkloadNodeControlSurfaceDeclaration(
        core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "internal"),
            (), health_reads=(core.NodeHealthReadKind.LIVENESS,),
        ), profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
    )


def _require_router_configuration(configuration: ReceiverNodeControlConfiguration) -> ReceiverNodeControlConfiguration:
    if (type(configuration) is not ReceiverNodeControlConfiguration
            or configuration.declaration != router_control_declaration()):
        raise ValueError
    return configuration


def decode_router_control_configuration(raw: bytes) -> ReceiverNodeControlConfiguration:
    """Decode common receiving values and enforce this product's declaration."""
    try:
        return _require_router_configuration(ReceiverNodeControlConfigurationCodec().decode_bytes(raw))
    except Exception:
        failure = RouterConfigurationError("Router control configuration is invalid")
    raise failure


def read_router_control_configuration() -> ReceiverNodeControlConfiguration:
    try:
        from control_plane_kit_server_sdk.wrapper import load_wrapper_configuration
        return _require_router_configuration(load_wrapper_configuration())
    except Exception:
        failure = RouterConfigurationError("Router control configuration is invalid")
    raise failure


def router_control_configuration_artifact(config: ReceiverNodeControlConfiguration) -> ConfigurationArtifact:
    try:
        content = ReceiverNodeControlConfigurationCodec().encode_bytes(config)
        decode_router_control_configuration(content)
        return ConfigurationArtifact("router-control", CONTROL_PATH, ConfigurationMediaType.JSON,
                                     content.decode("utf-8"), ConfigurationFileMode.READ_ONLY)
    except Exception:
        failure = RouterConfigurationError("Router control configuration is invalid")
    raise failure


def router_source_runtime_contract(artifact: ConfigurationArtifact) -> ProductRuntimeContract:
    """Source-only contract; does not replace the historical published descriptor."""
    try:
        if (type(artifact) is not ConfigurationArtifact or artifact.artifact_id != "router-control"
                or artifact.target_path != CONTROL_PATH or artifact.media_type is not ConfigurationMediaType.JSON
                or artifact.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        decode_router_control_configuration(artifact.content.encode("utf-8"))
        return ProductRuntimeContract(
            sockets=BlockSockets(
                requirements=(RequirementSocket("active", Protocol.HTTP, ("ACTIVE_TARGET_URL",)),),
                providers=(ProviderSocket("internal", Protocol.HTTP),)),
            provider_ports=(ProviderRuntimePort("internal", 8000),),
            configuration_artifacts=(artifact,),
            public_environment=(PublicStaticEnvironmentBinding(WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT, CONTROL_PATH),),
            capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(router_control_declaration().surface,),
            verification=VerificationContract(checks=(
                HttpCheck(check_id="live", provider_socket="internal", path="/health/live",
                          policy=VerificationPolicy(maximum_attempts=5)),
            )),
        )
    except Exception:
        failure = RouterConfigurationError("Router control configuration is invalid")
    raise failure


@dataclass(frozen=True, slots=True, repr=False)
class RouterSettings:
    """One startup target; production port policy belongs to main."""

    active_target_url: str
    port: int = 8000

    def __post_init__(self) -> None:
        accepted = False
        try:
            parsed = parse.urlparse(self.active_target_url)
            accepted = (type(self.active_target_url) is str
                        and parsed.scheme in {"http", "https"} and bool(parsed.netloc)
                        and type(self.port) is int and 0 < self.port < 65536)
        except Exception:
            accepted = False
        if not accepted:
            raise RouterConfigurationError("ACTIVE_TARGET_URL or PORT is invalid")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "RouterSettings":
        try:
            values = os.environ if environment is None else environment
            active_target_url = values.get("ACTIVE_TARGET_URL", "").strip()
            if not active_target_url:
                raise ValueError
            parsed = parse.urlparse(active_target_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError
            port = int(values.get("PORT", "8000"))
            return cls(active_target_url=active_target_url.rstrip("/"), port=port)
        except Exception:
            failure = RouterConfigurationError("ACTIVE_TARGET_URL or PORT is invalid")
        raise failure
