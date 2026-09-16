"""Public gateway health trust decoded from one exact product-owned artifact."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import json

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import control_plane_kit_core as core
from control_plane_kit_core._node_control_public_wire import reference_violation
from control_plane_kit_core.configuration import (
    ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType,
)
from control_plane_kit_core.node_health_transit import MAX_GATEWAY_NODE_HEALTH_READ_TRANSIT_AUDIENCE_BYTES


PROFILE = "cpk-gateway-health-transit-configuration.v1"
ARTIFACT_ID = "gateway-health-transit"
CONFIGURATION_PATH = "/etc/cpk/gateway/health-transit.json"
MAX_CONFIGURATION_BYTES = 16_384
_FIELDS = frozenset({"profile", "workspace_id", "gateway_node_id", "runtime_id",
    "issuer", "purpose", "public_keys"})
_KEY_FIELDS = frozenset({"key_id", "algorithm", "public_key_pem"})
_ERROR = "gateway health transit configuration is invalid"
_INPUT_ERRORS = (ValueError, TypeError, KeyError, AttributeError, RecursionError,
                 OverflowError, UnsupportedAlgorithm)


class GatewayHealthTransitConfigurationError(ValueError):
    """Fixed, candidate-free public configuration refusal."""


@dataclass(frozen=True, slots=True, repr=False)
class GatewayHealthTransitConfiguration:
    workspace_id: core.NodeControlGraphReference
    gateway_node_id: core.NodeControlGraphReference
    runtime_id: core.NodeControlGraphReference
    issuer: str
    purpose: core.DelegationKeyPurpose
    public_keys: tuple[core.DelegationPublicKey, ...] = field(repr=False)

    def __post_init__(self) -> None:
        try:
            roles = core.NodeControlGraphReferenceRole
            for value, role in ((self.workspace_id, roles.WORKSPACE),
                                (self.gateway_node_id, roles.NODE), (self.runtime_id, roles.RUNTIME)):
                if (type(value) is not core.NodeControlGraphReference or value.role is not role
                        or core.NodeControlGraphReference(role, value.value) != value):
                    raise ValueError
            if (type(self.issuer) is not str or reference_violation(self.issuer) is not None
                    or self.purpose is not core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT
                    or len(self.audience.encode("ascii")) > MAX_GATEWAY_NODE_HEALTH_READ_TRANSIT_AUDIENCE_BYTES):
                raise ValueError
            if type(self.public_keys) is not tuple or not 1 <= len(self.public_keys) <= 16:
                raise ValueError
            for key in self.public_keys:
                _public_key(key)
            if (len({key.key_id for key in self.public_keys}) != len(self.public_keys)
                    or len({key.fingerprint_sha256 for key in self.public_keys}) != len(self.public_keys)):
                raise ValueError
            object.__setattr__(self, "public_keys", tuple(sorted(self.public_keys, key=lambda key: key.key_id)))
            return
        except _INPUT_ERRORS:
            pass
        raise GatewayHealthTransitConfigurationError(_ERROR)

    @property
    def audience(self) -> str:
        return f"gateway:{self.workspace_id.value}:{self.gateway_node_id.value}"

    def __repr__(self) -> str:
        return "GatewayHealthTransitConfiguration(<redacted>)"


def _public_key(key: core.DelegationPublicKey) -> Ed25519PublicKey:
    if (type(key) is not core.DelegationPublicKey
            or type(key.key_id) is not str or type(key.public_key_pem) is not str
            or type(key.fingerprint_sha256) is not str
            or key.algorithm is not core.DelegationKeyAlgorithm.ED25519
            or len(key.public_key_pem.encode("ascii")) > 512
            or core.DelegationPublicKey(key.key_id, key.algorithm, key.public_key_pem) != key):
        raise ValueError
    parsed = serialization.load_pem_public_key(key.public_key_pem.encode("ascii"))
    if not isinstance(parsed, Ed25519PublicKey):
        raise ValueError
    # One canonical public identity prevents alternate PEM wrapping from making
    # the same material look like two distinct keys in an overlap snapshot.
    if parsed.public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo) != key.public_key_pem.encode("ascii"):
        raise ValueError
    return parsed


def _object(value: object, keys: frozenset[str]) -> dict:
    if type(value) is not dict or frozenset(value) != keys:
        raise ValueError
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError


def _structural_json(value: object, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError
    if type(value) is dict:
        for item in value.values():
            _structural_json(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _structural_json(item, depth + 1)
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError


def _decode_json(raw: bytes, maximum: int) -> object:
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum:
        raise ValueError
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
        parse_constant=_reject_constant)
    _structural_json(value)
    return value


def decode_gateway_health_transit_configuration(raw: bytes) -> GatewayHealthTransitConfiguration:
    try:
        value = _object(_decode_json(raw, MAX_CONFIGURATION_BYTES), _FIELDS)
        if (type(value["profile"]) is not str or value["profile"] != PROFILE
                or type(value["purpose"]) is not str
                or value["purpose"] != core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT.value
                or type(value["public_keys"]) is not list or not 1 <= len(value["public_keys"]) <= 16):
            raise ValueError
        keys = []
        for entry in value["public_keys"]:
            entry = _object(entry, _KEY_FIELDS)
            if any(type(entry[name]) is not str for name in _KEY_FIELDS):
                raise ValueError
            keys.append(core.DelegationPublicKey(entry["key_id"],
                core.DelegationKeyAlgorithm(entry["algorithm"]), entry["public_key_pem"]))
        roles = core.NodeControlGraphReferenceRole
        return GatewayHealthTransitConfiguration(
            core.NodeControlGraphReference(roles.WORKSPACE, value["workspace_id"]),
            core.NodeControlGraphReference(roles.NODE, value["gateway_node_id"]),
            core.NodeControlGraphReference(roles.RUNTIME, value["runtime_id"]),
            value["issuer"], core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, tuple(keys))
    except _INPUT_ERRORS:
        pass
    raise GatewayHealthTransitConfigurationError(_ERROR)


def gateway_health_transit_configuration_artifact(
    configuration: GatewayHealthTransitConfiguration,
) -> ConfigurationArtifact:
    try:
        if type(configuration) is not GatewayHealthTransitConfiguration:
            raise TypeError
        configuration = replace(configuration)
        content = json.dumps(dict(profile=PROFILE, workspace_id=configuration.workspace_id.value,
            gateway_node_id=configuration.gateway_node_id.value, runtime_id=configuration.runtime_id.value,
            issuer=configuration.issuer, purpose=configuration.purpose.value,
            public_keys=[dict(key_id=key.key_id, algorithm=key.algorithm.value,
                public_key_pem=key.public_key_pem) for key in configuration.public_keys]),
            ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        decode_gateway_health_transit_configuration(content.encode("utf-8"))
        return ConfigurationArtifact(ARTIFACT_ID, CONFIGURATION_PATH,
            ConfigurationMediaType.JSON, content, ConfigurationFileMode.READ_ONLY)
    except _INPUT_ERRORS:
        pass
    raise GatewayHealthTransitConfigurationError(_ERROR)


def _configuration_from_artifact(artifact: ConfigurationArtifact) -> GatewayHealthTransitConfiguration:
    try:
        if (type(artifact) is not ConfigurationArtifact or artifact.artifact_id != ARTIFACT_ID
                or artifact.target_path != CONFIGURATION_PATH
                or artifact.media_type is not ConfigurationMediaType.JSON
                or artifact.file_mode is not ConfigurationFileMode.READ_ONLY
                or type(artifact.content) is not str
                or not 1 <= len(artifact.content.encode("utf-8")) <= MAX_CONFIGURATION_BYTES):
            raise ValueError
        checked = ConfigurationArtifact.from_descriptor(artifact.descriptor())
        return decode_gateway_health_transit_configuration(checked.content.encode("utf-8"))
    except _INPUT_ERRORS:
        pass
    raise GatewayHealthTransitConfigurationError(_ERROR)
