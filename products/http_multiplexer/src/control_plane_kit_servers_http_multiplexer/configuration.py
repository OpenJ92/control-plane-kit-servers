"""Multiplexer's public, integrity-sensitive configuration and source contract."""
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

CONTROL_PATH = "/etc/cpk/multiplexer/control.json"
MAX_CONTROL_BYTES = 65_536
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")


class MultiplexerConfigurationError(ValueError):
    """Malformed Multiplexer startup configuration; never carries source material."""


def multiplexer_control_declaration() -> core.WorkloadNodeControlSurfaceDeclaration:
    return core.WorkloadNodeControlSurfaceDeclaration(
        core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "internal"),
            (), health_reads=(core.NodeHealthReadKind.LIVENESS,),
        ), profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
    )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class MultiplexerControlConfiguration:
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
                and self.declaration == multiplexer_control_declaration()
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
            raise MultiplexerConfigurationError("Multiplexer control configuration is invalid")


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


def decode_multiplexer_control_configuration(raw: bytes) -> MultiplexerControlConfiguration:
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_CONTROL_BYTES:
            raise ValueError
        value = _object(json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object),
                        {"profile", "target", "runtime_id", "declaration", "surface_read", "health_read"})
        if value["profile"] != "multiplexer-control-configuration.v1":
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
        return MultiplexerControlConfiguration(
            target=target, runtime_id=core.NodeControlGraphReference(roles.RUNTIME, value["runtime_id"]),
            declaration=core.WorkloadNodeControlSurfaceDeclarationCodec().decode(value["declaration"]),
            surface_issuer=surface_issuer, surface_keys=surface_keys,
            health_issuer=health_issuer, health_keys=health_keys,
        )
    except Exception:
        failure = MultiplexerConfigurationError("Multiplexer control configuration is invalid")
    raise failure


def read_multiplexer_control_configuration() -> MultiplexerControlConfiguration:
    try:
        descriptor = os.open(CONTROL_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError
            raw = stream.read(MAX_CONTROL_BYTES + 1)
        return decode_multiplexer_control_configuration(raw)
    except Exception:
        failure = MultiplexerConfigurationError("Multiplexer control configuration is invalid")
    raise failure


def multiplexer_control_configuration_artifact(config: MultiplexerControlConfiguration) -> ConfigurationArtifact:
    try:
        if type(config) is not MultiplexerControlConfiguration:
            raise ValueError
        def family(issuer, snapshot):
            return {"issuer": issuer, "public_keys": [
                {"key_id": key.key_id, "algorithm": key.algorithm.value, "public_key_pem": key.public_key_pem}
                for key in snapshot.public_keys
            ]}
        content = json.dumps({
            "profile": "multiplexer-control-configuration.v1", "target": config.target.descriptor(),
            "runtime_id": config.runtime_id.value, "declaration": config.declaration.descriptor(),
            "surface_read": family(config.surface_issuer, config.surface_keys),
            "health_read": family(config.health_issuer, config.health_keys),
        }, sort_keys=True, separators=(",", ":"))
        decode_multiplexer_control_configuration(content.encode("utf-8"))
        return ConfigurationArtifact("multiplexer-control", CONTROL_PATH, ConfigurationMediaType.JSON,
                                          content, ConfigurationFileMode.READ_ONLY)
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
