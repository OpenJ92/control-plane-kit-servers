"""Product artifact and declared-port policy over Core management routes.

Trusted composition owns graph/approval membership and hostname resolution. This
module frames canonical receiving values; it never grants dispatch authority.
"""
import re

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import (
    ConfigurationArtifact, ConfigurationArtifactRequirement, ConfigurationFileMode, ConfigurationMediaType,
)
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT
from control_plane_kit_core.products import ProductRuntimeContract, ProductRuntimeContractCodec, ProviderRuntimePort
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import VerificationContract
from .health_transit_configuration import _configuration_from_artifact, _INPUT_ERRORS
from .health_transit_configuration import ARTIFACT_ID as TRANSIT_ARTIFACT_ID, CONFIGURATION_PATH as TRANSIT_PATH
from .control_configuration import CONTROL_PATH, gateway_control_declaration

ARTIFACT_ID = "gateway-health-targets"
CONFIGURATION_PATH = "/etc/cpk/gateway/health-targets.json"
MAX_CONFIGURATION_BYTES = 131_072
_HOST = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\Z")
_ERROR = "gateway health relay configuration is invalid"


class GatewayHealthRelayConfigurationError(ValueError):
    """Bounded configuration failure without candidate context."""


def _hostname(value):
    if type(value) is not str or len(value) > 253 or _HOST.fullmatch(value) is None:
        raise ValueError
    return value


def gateway_health_target_binding(*, target_id, target, runtime_contract, hostname):
    """Select only the exact declared control provider; never enumerate edges."""
    try:
        if type(runtime_contract) is not ProductRuntimeContract or type(target) is not core.NodeControlReceiverTarget:
            raise ValueError
        contract = ProductRuntimeContractCodec().decode(runtime_contract.descriptor())
        socket = target.provider_socket_name.value
        surfaces = tuple(item for item in contract.control_surfaces if item.provider_socket_name.value == socket)
        ports = tuple(item for item in contract.provider_ports if item.provider_socket == socket)
        if len(surfaces) != 1 or len(ports) != 1 or contract.sockets.provider(socket).protocol is not Protocol.HTTP:
            raise ValueError
        declaration = core.WorkloadNodeControlSurfaceDeclaration(surfaces[0],
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)
        return core.ReceiverManagementRouteBinding(target_id, target, declaration,
            f"http://{_hostname(hostname)}:{ports[0].container_port}")
    except _INPUT_ERRORS:
        failure = GatewayHealthRelayConfigurationError(_ERROR)
    raise failure


def gateway_health_relay_configuration_artifact(configuration):
    try:
        content = core.ReceiverManagementRoutesCodec().encode_bytes(configuration)
        return ConfigurationArtifact(ARTIFACT_ID, CONFIGURATION_PATH, ConfigurationMediaType.JSON,
            content.decode(), ConfigurationFileMode.READ_ONLY)
    except _INPUT_ERRORS:
        failure = GatewayHealthRelayConfigurationError(_ERROR)
    raise failure


def gateway_health_declared_runtime_contract():
    """Declare capability and required public slots before instance trust exists."""
    return ProductRuntimeContract(
        sockets=BlockSockets(providers=(ProviderSocket("control", Protocol.HTTP),)),
        provider_ports=(ProviderRuntimePort("control", 8000),),
        configuration_requirements=tuple(ConfigurationArtifactRequirement(
            artifact_id, path, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY)
            for artifact_id, path in ((TRANSIT_ARTIFACT_ID, TRANSIT_PATH),
                (ARTIFACT_ID, CONFIGURATION_PATH), ("gateway-control", CONTROL_PATH))),
        gateway_transit=core.GatewayTransitDeclaration("control", core.GatewayTransitProtocol.RECEIVER_HEALTH_READ_V2),
        public_environment=(PublicStaticEnvironmentBinding(
            WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT, CONTROL_PATH),),
        capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
        control_surfaces=(gateway_control_declaration().surface,), verification=VerificationContract())


def gateway_health_source_runtime_contract(trust_artifact, targets_artifact, control_artifact):
    """Complete source contract with real own health; no image association."""
    try:
        from .control_configuration import gateway_control_configuration_from_artifact, require_matching_gateway_control
        trust = _configuration_from_artifact(trust_artifact)
        if type(targets_artifact) is not ConfigurationArtifact:
            raise ValueError
        artifact = ConfigurationArtifact.from_descriptor(targets_artifact.descriptor())
        if (artifact.artifact_id != ARTIFACT_ID or artifact.target_path != CONFIGURATION_PATH
                or artifact.media_type is not ConfigurationMediaType.JSON
                or artifact.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        targets = core.ReceiverManagementRoutesCodec().decode_bytes(artifact.content.encode())
        require_matching_receiver(trust, targets)
        control = gateway_control_configuration_from_artifact(control_artifact)
        require_matching_gateway_control(control, targets)
        return ProductRuntimeContract(sockets=BlockSockets(providers=(ProviderSocket("control", Protocol.HTTP),)),
            provider_ports=(ProviderRuntimePort("control", 8000),), configuration_artifacts=(trust_artifact, artifact, control_artifact),
            gateway_transit=core.GatewayTransitDeclaration("control", core.GatewayTransitProtocol.RECEIVER_HEALTH_READ_V2),
            public_environment=(PublicStaticEnvironmentBinding(
                WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT, control_artifact.target_path),),
            capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(control.declaration.surface,), verification=VerificationContract())
    except _INPUT_ERRORS:
        failure = GatewayHealthRelayConfigurationError(_ERROR)
    raise failure


def require_matching_receiver(trust, targets):
    if trust.gateway_target != targets.gateway_target:
        raise GatewayHealthRelayConfigurationError(_ERROR)
