"""Public, integrity-sensitive trust for the gateway's own SDK receiver."""
from dataclasses import dataclass
import json
import os
import stat

import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_server_sdk.verifier_keys import (
    WorkloadNodeControlSurfaceReadVerifierKeySet, WorkloadNodeHealthReadVerifierKeySet,
)
from .health_transit_configuration import _decode_json, _object, _public_key, _INPUT_ERRORS, reference_violation

CONTROL_PATH = "/etc/cpk/gateway/control.json"
MAX_CONTROL_BYTES = 65536
PROFILE = "cpk-gateway-control-configuration.v1"
_ERROR = "gateway control configuration is invalid"


class GatewayControlConfigurationError(ValueError):
    """Fixed refusal without candidate material or exception chains."""


def gateway_control_declaration():
    return core.WorkloadNodeControlSurfaceDeclaration(core.WorkloadNodeControlSurfaceDescriptor(
        core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "control"), (),
        health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)),
        profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)


def _target(value):
    value = _object(value, frozenset({"workspace_id", "graph_revision", "node_id", "provider_socket_name"}))
    roles = core.NodeControlGraphReferenceRole
    return core.NodeControlTarget(*(core.NodeControlGraphReference(role, value[name]) for name, role in (
        ("workspace_id", roles.WORKSPACE), ("graph_revision", roles.GRAPH_REVISION),
        ("node_id", roles.NODE), ("provider_socket_name", roles.PROVIDER_SOCKET))))


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class GatewayControlConfiguration:
    target: core.NodeControlTarget
    runtime_id: core.NodeControlGraphReference
    declaration: core.WorkloadNodeControlSurfaceDeclaration
    surface_issuer: str
    surface_keys: WorkloadNodeControlSurfaceReadVerifierKeySet
    health_issuer: str
    health_keys: WorkloadNodeHealthReadVerifierKeySet

    def __post_init__(self):
        try:
            if (type(self.target) is not core.NodeControlTarget or _target(self.target.descriptor()) != self.target
                    or type(self.runtime_id) is not core.NodeControlGraphReference
                    or self.runtime_id.role is not core.NodeControlGraphReferenceRole.RUNTIME
                    or core.NodeControlGraphReference(self.runtime_id.role, self.runtime_id.value) != self.runtime_id
                    or type(self.declaration) is not core.WorkloadNodeControlSurfaceDeclaration
                    or self.declaration != gateway_control_declaration()
                    or self.target.provider_socket_name != self.declaration.surface.provider_socket_name):
                raise ValueError
            for issuer, snapshot, snapshot_type, purpose in (
                (self.surface_issuer, self.surface_keys, WorkloadNodeControlSurfaceReadVerifierKeySet,
                    core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ),
                (self.health_issuer, self.health_keys, WorkloadNodeHealthReadVerifierKeySet,
                    core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)):
                if (type(issuer) is not str or reference_violation(issuer) is not None
                        or type(snapshot) is not snapshot_type or snapshot.purpose is not purpose
                        or type(snapshot.public_keys) is not tuple or not 1 <= len(snapshot.public_keys) <= 16):
                    raise ValueError
                for key in snapshot.public_keys:
                    _public_key(key)
                if snapshot_type(purpose, snapshot.public_keys) != snapshot:
                    raise ValueError
            return
        except _INPUT_ERRORS:
            failure = GatewayControlConfigurationError(_ERROR)
        raise failure


def _family(value, snapshot_type, purpose):
    value = _object(value, frozenset({"issuer", "public_keys"}))
    if type(value["public_keys"]) is not list or not 1 <= len(value["public_keys"]) <= 16:
        raise ValueError
    keys = []
    for entry in value["public_keys"]:
        entry = _object(entry, frozenset({"key_id", "algorithm", "public_key_pem"}))
        keys.append(core.DelegationPublicKey(entry["key_id"], core.DelegationKeyAlgorithm(entry["algorithm"]), entry["public_key_pem"]))
    return value["issuer"], snapshot_type(purpose, tuple(keys))


def decode_gateway_control_configuration(raw):
    try:
        value = _object(_decode_json(raw, MAX_CONTROL_BYTES),
            frozenset({"profile", "target", "runtime_id", "declaration", "surface_read", "health_read"}))
        if value["profile"] != PROFILE:
            raise ValueError
        surface_issuer, surface_keys = _family(value["surface_read"], WorkloadNodeControlSurfaceReadVerifierKeySet,
            core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ)
        health_issuer, health_keys = _family(value["health_read"], WorkloadNodeHealthReadVerifierKeySet,
            core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)
        return GatewayControlConfiguration(target=_target(value["target"]),
            runtime_id=core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.RUNTIME, value["runtime_id"]),
            declaration=core.WorkloadNodeControlSurfaceDeclarationCodec().decode(value["declaration"]),
            surface_issuer=surface_issuer, surface_keys=surface_keys, health_issuer=health_issuer, health_keys=health_keys)
    except _INPUT_ERRORS:
        failure = GatewayControlConfigurationError(_ERROR)
    raise failure


def gateway_control_configuration_artifact(configuration):
    try:
        if type(configuration) is not GatewayControlConfiguration:
            raise ValueError
        def family(issuer, snapshot):
            return {"issuer":issuer, "public_keys":[{"key_id":key.key_id, "algorithm":key.algorithm.value,
                "public_key_pem":key.public_key_pem} for key in snapshot.public_keys]}
        content = json.dumps({"profile":PROFILE, "target":configuration.target.descriptor(),
            "runtime_id":configuration.runtime_id.value, "declaration":configuration.declaration.descriptor(),
            "surface_read":family(configuration.surface_issuer, configuration.surface_keys),
            "health_read":family(configuration.health_issuer, configuration.health_keys)}, sort_keys=True, separators=(",", ":"))
        decode_gateway_control_configuration(content.encode())
        return ConfigurationArtifact("gateway-control", CONTROL_PATH, ConfigurationMediaType.JSON,
            content, ConfigurationFileMode.READ_ONLY)
    except _INPUT_ERRORS:
        failure = GatewayControlConfigurationError(_ERROR)
    raise failure


def gateway_control_configuration_from_artifact(artifact):
    try:
        if type(artifact) is not ConfigurationArtifact:
            raise ValueError
        artifact = ConfigurationArtifact.from_descriptor(artifact.descriptor())
        if (artifact.artifact_id != "gateway-control" or artifact.target_path != CONTROL_PATH
                or artifact.media_type is not ConfigurationMediaType.JSON or artifact.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        return decode_gateway_control_configuration(artifact.content.encode())
    except _INPUT_ERRORS:
        failure = GatewayControlConfigurationError(_ERROR)
    raise failure


def read_gateway_control_configuration():
    try:
        def opener(path, flags):
            return os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with open(CONTROL_PATH, "rb", opener=opener) as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError
            raw = stream.read(MAX_CONTROL_BYTES + 1)
        return decode_gateway_control_configuration(raw)
    except (OSError, *_INPUT_ERRORS):
        failure = GatewayControlConfigurationError(_ERROR)
    raise failure


def require_matching_gateway_control(control, relay):
    if (control.target.workspace_id != relay.workspace_id or control.target.node_id != relay.gateway_node_id
            or control.runtime_id != relay.runtime_id):
        raise GatewayControlConfigurationError(_ERROR)
