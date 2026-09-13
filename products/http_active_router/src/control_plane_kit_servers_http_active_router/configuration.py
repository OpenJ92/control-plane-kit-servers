"""Router's public, integrity-sensitive configuration and source contract."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import stat
from typing import Mapping
from urllib import parse

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket, RequirementSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType, ConfigurationFileMode
from control_plane_kit_core.products import ProductRuntimeContract, ProviderRuntimePort
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import VerificationContract, VerificationPolicy, HttpCheck
from control_plane_kit_server_sdk.verifier_keys import (
    WorkloadNodeControlSurfaceReadVerifierKeySet, WorkloadNodeHealthReadVerifierKeySet,
)

CONTROL_PATH = "/etc/cpk/router/control.json"
MAX_CONTROL_BYTES = 65_536
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")


class RouterConfigurationError(ValueError):
    """Malformed Router startup configuration; never carries source material."""


def router_control_declaration() -> core.WorkloadNodeControlSurfaceDeclaration:
    return core.WorkloadNodeControlSurfaceDeclaration(
        core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "internal"),
            (), health_reads=(core.NodeHealthReadKind.LIVENESS,),
        ), profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
    )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class RouterControlConfiguration:
    target: core.NodeControlTarget
    runtime_id: core.NodeControlGraphReference
    declaration: core.WorkloadNodeControlSurfaceDeclaration
    surface_issuer: str
    surface_keys: WorkloadNodeControlSurfaceReadVerifierKeySet
    health_issuer: str
    health_keys: WorkloadNodeHealthReadVerifierKeySet

    def __post_init__(self) -> None:
        valid = False
        try:
            valid = (
                type(self.target) is core.NodeControlTarget
                and type(self.runtime_id) is core.NodeControlGraphReference
                and self.runtime_id.role is core.NodeControlGraphReferenceRole.RUNTIME
                and self.declaration == router_control_declaration()
                and type(self.declaration) is core.WorkloadNodeControlSurfaceDeclaration
                and self.target.provider_socket_name == self.declaration.surface.provider_socket_name
                and type(self.surface_keys) is WorkloadNodeControlSurfaceReadVerifierKeySet
                and type(self.health_keys) is WorkloadNodeHealthReadVerifierKeySet
                and all(type(value) is str and _REFERENCE.fullmatch(value)
                        for value in (self.surface_issuer, self.health_issuer,
                                      core.workload_node_control_audience(self.target)))
            )
        except Exception:
            valid = False
        if not valid:
            raise RouterConfigurationError("Router control configuration is invalid")


def _object(value: object, keys: set[str]) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValueError
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _family(value: object, snapshot_type, purpose):
    value = _object(value, {"issuer", "public_keys"})
    entries = value["public_keys"]
    if type(entries) is not list or not 1 <= len(entries) <= 16:
        raise ValueError
    keys = []
    for entry in entries:
        entry = _object(entry, {"key_id", "algorithm", "public_key_pem"})
        keys.append(core.DelegationPublicKey(
            entry["key_id"], core.DelegationKeyAlgorithm(entry["algorithm"]), entry["public_key_pem"],
        ))
    return value["issuer"], snapshot_type(purpose, tuple(keys))


def decode_router_control_configuration(raw: bytes) -> RouterControlConfiguration:
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_CONTROL_BYTES:
            raise ValueError
        value = _object(json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object),
                        {"profile", "target", "runtime_id", "declaration", "surface_read", "health_read"})
        if value["profile"] != "router-control-configuration.v1":
            raise ValueError
        target = _object(value["target"], {"workspace_id", "graph_revision", "node_id", "provider_socket_name"})
        roles = core.NodeControlGraphReferenceRole
        target = core.NodeControlTarget(**{
            name: core.NodeControlGraphReference(role, target[name])
            for name, role in (("workspace_id", roles.WORKSPACE), ("graph_revision", roles.GRAPH_REVISION),
                               ("node_id", roles.NODE), ("provider_socket_name", roles.PROVIDER_SOCKET))
        })
        surface_issuer, surface_keys = _family(value["surface_read"], WorkloadNodeControlSurfaceReadVerifierKeySet,
                                              core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ)
        health_issuer, health_keys = _family(value["health_read"], WorkloadNodeHealthReadVerifierKeySet,
                                           core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)
        return RouterControlConfiguration(
            target=target, runtime_id=core.NodeControlGraphReference(roles.RUNTIME, value["runtime_id"]),
            declaration=core.WorkloadNodeControlSurfaceDeclarationCodec().decode(value["declaration"]),
            surface_issuer=surface_issuer, surface_keys=surface_keys,
            health_issuer=health_issuer, health_keys=health_keys,
        )
    except Exception:
        failure = RouterConfigurationError("Router control configuration is invalid")
    raise failure


def read_router_control_configuration() -> RouterControlConfiguration:
    try:
        descriptor = os.open(CONTROL_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError
            raw = stream.read(MAX_CONTROL_BYTES + 1)
        return decode_router_control_configuration(raw)
    except Exception:
        failure = RouterConfigurationError("Router control configuration is invalid")
    raise failure


def router_control_configuration_artifact(config: RouterControlConfiguration) -> ConfigurationArtifact:
    try:
        if type(config) is not RouterControlConfiguration:
            raise ValueError
        def family(issuer, snapshot):
            return {"issuer": issuer, "public_keys": [
                {"key_id": key.key_id, "algorithm": key.algorithm.value, "public_key_pem": key.public_key_pem}
                for key in snapshot.public_keys
            ]}
        content = json.dumps({
            "profile": "router-control-configuration.v1", "target": config.target.descriptor(),
            "runtime_id": config.runtime_id.value, "declaration": config.declaration.descriptor(),
            "surface_read": family(config.surface_issuer, config.surface_keys),
            "health_read": family(config.health_issuer, config.health_keys),
        }, sort_keys=True, separators=(",", ":"))
        decode_router_control_configuration(content.encode("utf-8"))
        return ConfigurationArtifact("router-control", CONTROL_PATH, ConfigurationMediaType.JSON,
                                          content, ConfigurationFileMode.READ_ONLY)
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
