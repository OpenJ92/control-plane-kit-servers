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
from control_plane_kit_core.products import ProductRuntimeContract, ProductRuntimeContractCodec, ProviderRuntimePort
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import VerificationContract
from .health_transit_configuration import _decode_json, _object, _configuration_from_artifact, _INPUT_ERRORS

PROFILE = "cpk-gateway-health-relay-configuration.v1"
ARTIFACT_ID = "gateway-health-targets"
CONFIGURATION_PATH = "/etc/cpk/gateway/health-targets.json"
MAX_CONFIGURATION_BYTES = 131_072
_ID = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_HOST = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\Z")
_FIELDS = frozenset({"profile", "workspace_id", "gateway_node_id", "runtime_id", "targets"})
_BINDING_FIELDS = frozenset({"target_id", "target", "runtime_id", "declaration", "origin"})
_TARGET_FIELDS = frozenset({"workspace_id", "graph_revision", "node_id", "provider_socket_name"})
_ERROR = "gateway health relay configuration is invalid"


class GatewayHealthRelayConfigurationError(ValueError):
    """Bounded configuration failure without candidate context."""


def _reference(value, role):
    if type(value) is not core.NodeControlGraphReference or value.role is not role:
        raise ValueError
    return core.NodeControlGraphReference(role, value.value)


def _hostname(value):
    if type(value) is not str or len(value) > 253 or _HOST.fullmatch(value) is None:
        raise ValueError
    return value


def _target(raw):
    value = _object(raw, _TARGET_FIELDS)
    roles = core.NodeControlGraphReferenceRole
    return core.NodeControlTarget(*(core.NodeControlGraphReference(role, value[name]) for name, role in (
        ("workspace_id", roles.WORKSPACE), ("graph_revision", roles.GRAPH_REVISION),
        ("node_id", roles.NODE), ("provider_socket_name", roles.PROVIDER_SOCKET))))


@dataclass(frozen=True, slots=True, repr=False)
class GatewayHealthTargetBinding:
    target_id: str
    target: core.NodeControlTarget
    runtime_id: core.NodeControlGraphReference
    declaration: core.WorkloadNodeControlSurfaceDeclaration
    origin: str

    def __post_init__(self):
        try:
            if type(self.target_id) is not str or _ID.fullmatch(self.target_id) is None:
                raise ValueError
            if type(self.target) is not core.NodeControlTarget or _target(self.target.descriptor()) != self.target:
                raise ValueError
            _reference(self.runtime_id, core.NodeControlGraphReferenceRole.RUNTIME)
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
        return dict(target_id=self.target_id, target=self.target.descriptor(), runtime_id=self.runtime_id.value,
                    declaration=self.declaration.descriptor(), origin=self.origin)


def gateway_health_target_binding(*, target_id, target, runtime_id, runtime_contract, hostname):
    """Select only the exact declared control provider; never enumerate edges."""
    try:
        if type(runtime_contract) is not ProductRuntimeContract or type(target) is not core.NodeControlTarget:
            raise ValueError
        contract = ProductRuntimeContractCodec().decode(runtime_contract.descriptor())
        socket = target.provider_socket_name.value
        surfaces = tuple(item for item in contract.control_surfaces if item.provider_socket_name.value == socket)
        ports = tuple(item for item in contract.provider_ports if item.provider_socket == socket)
        if len(surfaces) != 1 or len(ports) != 1 or contract.sockets.provider(socket).protocol is not Protocol.HTTP:
            raise ValueError
        declaration = core.WorkloadNodeControlSurfaceDeclaration(surfaces[0],
            profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)
        return GatewayHealthTargetBinding(target_id, target, runtime_id, declaration,
            f"http://{_hostname(hostname)}:{ports[0].container_port}")
    except _INPUT_ERRORS:
        failure = GatewayHealthRelayConfigurationError(_ERROR)
    raise failure


@dataclass(frozen=True, slots=True, repr=False)
class GatewayHealthRelayConfiguration:
    workspace_id: core.NodeControlGraphReference
    gateway_node_id: core.NodeControlGraphReference
    runtime_id: core.NodeControlGraphReference
    targets: tuple[GatewayHealthTargetBinding, ...]

    def __post_init__(self):
        try:
            roles = core.NodeControlGraphReferenceRole
            for value, role in ((self.workspace_id, roles.WORKSPACE), (self.gateway_node_id, roles.NODE),
                                (self.runtime_id, roles.RUNTIME)):
                _reference(value, role)
            if type(self.targets) is not tuple or len(self.targets) > 128:
                raise ValueError
            admitted = []
            for item in self.targets:
                if type(item) is not GatewayHealthTargetBinding:
                    raise ValueError
                item = replace(item)
                if item.target.workspace_id != self.workspace_id or item.runtime_id != self.runtime_id:
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
        return dict(profile=PROFILE, workspace_id=self.workspace_id.value, gateway_node_id=self.gateway_node_id.value,
            runtime_id=self.runtime_id.value, targets=[item.descriptor() for item in self.targets])


def _encode(value):
    return json.dumps(value.descriptor(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def decode_gateway_health_relay_configuration(raw):
    try:
        value = _object(_decode_json(raw, MAX_CONFIGURATION_BYTES), _FIELDS)
        if value["profile"] != PROFILE or type(value["targets"]) is not list or len(value["targets"]) > 128:
            raise ValueError
        roles = core.NodeControlGraphReferenceRole
        bindings = []
        for entry in value["targets"]:
            entry = _object(entry, _BINDING_FIELDS)
            bindings.append(GatewayHealthTargetBinding(entry["target_id"], _target(entry["target"]),
                core.NodeControlGraphReference(roles.RUNTIME, entry["runtime_id"]),
                core.WorkloadNodeControlSurfaceDeclarationCodec().decode(entry["declaration"]), entry["origin"]))
        return GatewayHealthRelayConfiguration(core.NodeControlGraphReference(roles.WORKSPACE, value["workspace_id"]),
            core.NodeControlGraphReference(roles.NODE, value["gateway_node_id"]),
            core.NodeControlGraphReference(roles.RUNTIME, value["runtime_id"]), tuple(bindings))
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
            gateway_transit=core.GatewayTransitDeclaration("control", core.GatewayTransitProtocol.NODE_HEALTH_READ_V1),
            capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(control.declaration.surface,), verification=VerificationContract())
    except _INPUT_ERRORS:
        failure = GatewayHealthRelayConfigurationError(_ERROR)
    raise failure


def require_matching_receiver(trust, targets):
    if any(getattr(trust, name) != getattr(targets, name) for name in ("workspace_id", "gateway_node_id", "runtime_id")):
        raise GatewayHealthRelayConfigurationError(_ERROR)
