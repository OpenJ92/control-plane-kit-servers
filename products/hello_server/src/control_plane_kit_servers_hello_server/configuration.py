"""Hello's public, integrity-sensitive configuration and source contract."""
from __future__ import annotations

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket
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

CONTROL_PATH = "/etc/cpk/hello/control.json"
MAX_CONTROL_BYTES = 65_536


class HelloConfigurationError(ValueError):
    """Malformed Hello startup configuration; never carries source material."""


def hello_control_declaration() -> core.WorkloadNodeControlSurfaceDeclaration:
    return core.WorkloadNodeControlSurfaceDeclaration(
        core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "internal"),
            (), health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS),
        ), profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
    )


def _require_hello_configuration(configuration: ReceiverNodeControlConfiguration) -> ReceiverNodeControlConfiguration:
    if (type(configuration) is not ReceiverNodeControlConfiguration
            or configuration.declaration != hello_control_declaration()):
        raise ValueError
    return configuration


def decode_hello_control_configuration(raw: bytes) -> ReceiverNodeControlConfiguration:
    """Decode common receiving values and enforce this product's declaration."""
    try:
        return _require_hello_configuration(ReceiverNodeControlConfigurationCodec().decode_bytes(raw))
    except Exception:
        failure = HelloConfigurationError("Hello control configuration is invalid")
    raise failure


def read_hello_control_configuration() -> ReceiverNodeControlConfiguration:
    try:
        from control_plane_kit_server_sdk.wrapper import load_wrapper_configuration
        return _require_hello_configuration(load_wrapper_configuration())
    except Exception:
        failure = HelloConfigurationError("Hello control configuration is invalid")
    raise failure


def hello_control_configuration_artifact(config: ReceiverNodeControlConfiguration) -> ConfigurationArtifact:
    try:
        content = ReceiverNodeControlConfigurationCodec().encode_bytes(config)
        decode_hello_control_configuration(content)
        return ConfigurationArtifact("hello-control", CONTROL_PATH, ConfigurationMediaType.JSON,
                                     content.decode("utf-8"), ConfigurationFileMode.READ_ONLY)
    except Exception:
        failure = HelloConfigurationError("Hello control configuration is invalid")
    raise failure


def hello_source_runtime_contract(artifact: ConfigurationArtifact) -> ProductRuntimeContract:
    """Source-only contract; does not replace the historical published descriptor."""
    try:
        if (type(artifact) is not ConfigurationArtifact or artifact.artifact_id != "hello-control"
                or artifact.target_path != CONTROL_PATH or artifact.media_type is not ConfigurationMediaType.JSON
                or artifact.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        decode_hello_control_configuration(artifact.content.encode("utf-8"))
        return ProductRuntimeContract(
            sockets=BlockSockets(providers=(ProviderSocket("internal", Protocol.HTTP),)),
            provider_ports=(ProviderRuntimePort("internal", 8000),),
            configuration_artifacts=(artifact,),
            public_environment=(PublicStaticEnvironmentBinding(WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT, CONTROL_PATH),
                                PublicStaticEnvironmentBinding("HELLO_MESSAGE", "Hello, world!"),
                                PublicStaticEnvironmentBinding("HELLO_COLOR", "blue"),
                                PublicStaticEnvironmentBinding("HELLO_DEPENDENCIES_JSON", "[]")),
            capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(hello_control_declaration().surface,),
            verification=VerificationContract(checks=(
                HttpCheck(check_id="live", provider_socket="internal", path="/health/live",
                          policy=VerificationPolicy(maximum_attempts=5)),
                HttpCheck(check_id="ready", provider_socket="internal", path="/health/ready",
                          policy=VerificationPolicy(maximum_attempts=5)),
            )),
        )
    except Exception:
        failure = HelloConfigurationError("Hello control configuration is invalid")
    raise failure
