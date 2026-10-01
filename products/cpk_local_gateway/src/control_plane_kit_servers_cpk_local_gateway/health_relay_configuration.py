"""Immutable receiving bindings for explicitly selected management HTTP sockets.

Trusted composition owns graph/approval membership and hostname resolution. This
module validates and frames receiving values; it never grants dispatch authority.
"""
from dataclasses import dataclass, replace
import json
import re
from urllib.parse import urlsplit

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT
from control_plane_kit_core.products import ProductRuntimeContract, ProductRuntimeContractCodec, ProviderRuntimePort
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import VerificationContract
from .health_transit_configuration import _decode_json, _object, _configuration_from_artifact, _INPUT_ERRORS

PROFILE = "cpk-gateway-health-relay-configuration.v2"
ARTIFACT_ID = "gateway-health-targets"
CONFIGURATION_PATH = "/etc/cpk/gateway/health-targets.json"
MAX_CONFIGURATION_BYTES = 131_072
_ID = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_HOST = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\Z")
_FIELDS = frozenset({"profile", "gateway_target", "targets"})
_BINDING_FIELDS = frozenset({"target_id", "target", "declaration", "origin"})
_ERROR = "gateway health relay configuration is invalid"


class GatewayHealthRelayConfigurationError(ValueError):
    """Bounded configuration failure without candidate context."""


def _hostname(value):
    if type(value) is not str or len(value) > 253 or _HOST.fullmatch(value) is None:
        raise ValueError
    return value


def _target(raw):
    return core.NodeControlReceiverTargetCodec().decode(raw)


@dataclass(frozen=True, slots=True, repr=False)
class GatewayHealthTargetBinding:
    target_id: str
    target: core.NodeControlReceiverTarget
    declaration: core.WorkloadNodeControlSurfaceDeclaration
    origin: str

    def __post_init__(self):
        try:
            if type(self.target_id) is not str or _ID.fullmatch(self.target_id) is None:
                raise ValueError
            if type(self.target) is not core.NodeControlReceiverTarget or _target(self.target.descriptor()) != self.target:
                raise ValueError
            if type(self.declaration) is not core.WorkloadNodeControlSurfaceDeclaration:
                raise ValueError
            declaration = core.WorkloadNodeControlSurfaceDeclarationCodec().decode(self.declaration.descriptor())
            if (declaration != self.declaration or declaration.profile is not core.WorkloadNodeControlSurfaceDeclarationProfile.V2
                    or declaration.surface.provider_socket_name != self.target.provider_socket_name):
                raise ValueError
            if type(self.origin) is not str:
                raise ValueError
            parsed = urlsplit(self.origin)
            host = _hostname(parsed.hostname)
            if (parsed.scheme != "http" or parsed.username is not None or parsed.password is not None
                    or parsed.path or parsed.query or parsed.fragment or parsed.port is None
                    or not 1 <= parsed.port <= 65535 or self.origin != f"http://{host}:{parsed.port}"):
                raise ValueError
            return
        except _INPUT_ERRORS:
            failure = GatewayHealthRelayConfigurationError(_ERROR)
        raise failure

    def descriptor(self):
        return dict(target_id=self.target_id, target=self.target.descriptor(),
                    declaration=self.declaration.descriptor(), origin=self.origin)


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
        return GatewayHealthTargetBinding(target_id, target, declaration,
            f"http://{_hostname(hostname)}:{ports[0].container_port}")
    except _INPUT_ERRORS:
        failure = GatewayHealthRelayConfigurationError(_ERROR)
    raise failure


@dataclass(frozen=True, slots=True, repr=False)
class GatewayHealthRelayConfiguration:
    gateway_target: core.NodeControlReceiverTarget
    targets: tuple[GatewayHealthTargetBinding, ...]

    def __post_init__(self):
        try:
            if (type(self.gateway_target) is not core.NodeControlReceiverTarget
                    or _target(self.gateway_target.descriptor()) != self.gateway_target):
                raise ValueError
            if type(self.targets) is not tuple or len(self.targets) > 128:
                raise ValueError
            admitted = []
            for item in self.targets:
                if type(item) is not GatewayHealthTargetBinding:
                    raise ValueError
                item = replace(item)
                if item.target.workspace_id != self.gateway_target.workspace_id or item.target.runtime_id != self.gateway_target.runtime_id:
                    raise ValueError
                admitted.append(item)
            if (len({item.target_id for item in admitted}) != len(admitted)
                    or len({item.target for item in admitted}) != len(admitted)):
                raise ValueError
            object.__setattr__(self, "targets", tuple(sorted(admitted, key=lambda item:item.target_id)))
            if len(_encode(self)) > MAX_CONFIGURATION_BYTES:
                raise ValueError
            return
        except _INPUT_ERRORS:
            failure = GatewayHealthRelayConfigurationError(_ERROR)
        raise failure

    def descriptor(self):
        return dict(profile=PROFILE, gateway_target=self.gateway_target.descriptor(), targets=[item.descriptor() for item in self.targets])


def _encode(value):
    return json.dumps(value.descriptor(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def decode_gateway_health_relay_configuration(raw):
    try:
        value = _object(_decode_json(raw, MAX_CONFIGURATION_BYTES), _FIELDS)
        if value["profile"] != PROFILE or type(value["targets"]) is not list or len(value["targets"]) > 128:
            raise ValueError
        bindings = []
        for entry in value["targets"]:
            entry = _object(entry, _BINDING_FIELDS)
            bindings.append(GatewayHealthTargetBinding(entry["target_id"], _target(entry["target"]),
                core.WorkloadNodeControlSurfaceDeclarationCodec().decode(entry["declaration"]), entry["origin"]))
        return GatewayHealthRelayConfiguration(_target(value["gateway_target"]), tuple(bindings))
    except _INPUT_ERRORS:
        failure = GatewayHealthRelayConfigurationError(_ERROR)
    raise failure


def gateway_health_relay_configuration_artifact(configuration):
    try:
        if type(configuration) is not GatewayHealthRelayConfiguration:
            raise ValueError
        content = _encode(replace(configuration))
        decode_gateway_health_relay_configuration(content)
        return ConfigurationArtifact(ARTIFACT_ID, CONFIGURATION_PATH, ConfigurationMediaType.JSON,
            content.decode(), ConfigurationFileMode.READ_ONLY)
    except _INPUT_ERRORS:
        failure = GatewayHealthRelayConfigurationError(_ERROR)
    raise failure


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
        targets = decode_gateway_health_relay_configuration(artifact.content.encode())
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
