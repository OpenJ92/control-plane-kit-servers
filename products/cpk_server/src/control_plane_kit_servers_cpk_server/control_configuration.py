"""CPK's public, integrity-sensitive configuration and source contract."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import stat
from enum import StrEnum

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket, RequirementSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType, ConfigurationFileMode
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.secrets import SecretEnvironmentDelivery, SecretReference, SecretUseIntent
from control_plane_kit_core.products import ProductRuntimeContract, ProviderRuntimePort
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import VerificationContract, VerificationPolicy, HttpCheck
from control_plane_kit_server_sdk.verifier_keys import (
    WorkloadNodeControlSurfaceReadVerifierKeySet, WorkloadNodeHealthReadVerifierKeySet,
)

CONTROL_PATH = "/etc/cpk/cpk-server/control.json"
MAX_CONTROL_BYTES = 65_536
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")


class CpkControlConfigurationError(ValueError):
    """Malformed CPK startup configuration; never carries source material."""


def cpk_control_declaration() -> core.WorkloadNodeControlSurfaceDeclaration:
    return core.WorkloadNodeControlSurfaceDeclaration(
        core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "http-api"),
            (), health_reads=(core.NodeHealthReadKind.LIVENESS,),
        ), profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
    )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CpkControlConfiguration:
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
                and self.declaration == cpk_control_declaration()
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
            raise CpkControlConfigurationError("CPK control configuration is invalid")


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


def decode_cpk_control_configuration(raw: bytes) -> CpkControlConfiguration:
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_CONTROL_BYTES:
            raise ValueError
        value = _object(json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object),
                        {"profile", "target", "runtime_id", "declaration", "surface_read", "health_read"})
        if value["profile"] != "cpk-control-configuration.v1":
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
        return CpkControlConfiguration(
            target=target, runtime_id=core.NodeControlGraphReference(roles.RUNTIME, value["runtime_id"]),
            declaration=core.WorkloadNodeControlSurfaceDeclarationCodec().decode(value["declaration"]),
            surface_issuer=surface_issuer, surface_keys=surface_keys,
            health_issuer=health_issuer, health_keys=health_keys,
        )
    except Exception:
        failure = CpkControlConfigurationError("CPK control configuration is invalid")
    raise failure


def read_cpk_control_configuration() -> CpkControlConfiguration:
    try:
        descriptor = os.open(CONTROL_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError
            raw = stream.read(MAX_CONTROL_BYTES + 1)
        return decode_cpk_control_configuration(raw)
    except Exception:
        failure = CpkControlConfigurationError("CPK control configuration is invalid")
    raise failure


def cpk_control_configuration_artifact(config: CpkControlConfiguration) -> ConfigurationArtifact:
    try:
        if type(config) is not CpkControlConfiguration:
            raise ValueError
        def family(issuer, snapshot):
            return {"issuer": issuer, "public_keys": [
                {"key_id": key.key_id, "algorithm": key.algorithm.value, "public_key_pem": key.public_key_pem}
                for key in snapshot.public_keys
            ]}
        content = json.dumps({
            "profile": "cpk-control-configuration.v1", "target": config.target.descriptor(),
            "runtime_id": config.runtime_id.value, "declaration": config.declaration.descriptor(),
            "surface_read": family(config.surface_issuer, config.surface_keys),
            "health_read": family(config.health_issuer, config.health_keys),
        }, sort_keys=True, separators=(",", ":"))
        decode_cpk_control_configuration(content.encode("utf-8"))
        return ConfigurationArtifact("cpk-control", CONTROL_PATH, ConfigurationMediaType.JSON,
                                          content, ConfigurationFileMode.READ_ONLY)
    except Exception:
        failure = CpkControlConfigurationError("CPK control configuration is invalid")
    raise failure


class CpkSourceVariant(StrEnum):
    CPK = "cpk-server"
    DOCKER = "cpk-server-docker"
    DOCKER_CLOUDFLARE = "cpk-server-docker-cloudflare"


def cpk_source_runtime_contract(
    variant: CpkSourceVariant, artifact: ConfigurationArtifact,
) -> ProductRuntimeContract:
    """Required source receiver for each variant; historical images stay separate."""
    try:
        if (type(variant) is not CpkSourceVariant or type(artifact) is not ConfigurationArtifact
                or artifact.artifact_id != "cpk-control" or artifact.target_path != CONTROL_PATH
                or artifact.media_type is not ConfigurationMediaType.JSON
                or artifact.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        decode_cpk_control_configuration(artifact.content.encode("utf-8"))
        environment = {
            "CPK_CONTROL_AUTH_CONFIGURED":"true", "CPK_PORT":"8080",
            "CPK_SERVER_MODE":"execution-capable",
            "CPK_RUNTIME_INTERPRETERS":"none" if variant is CpkSourceVariant.CPK else "docker",
            "CPK_INGRESS_INTERPRETERS":"cloudflare" if variant is CpkSourceVariant.DOCKER_CLOUDFLARE else "none",
        }
        if variant is not CpkSourceVariant.CPK:
            environment["CPK_PRODUCT_MATERIAL_RESOLVER"] = "provider"
        return ProductRuntimeContract(
            sockets=BlockSockets(
                requirements=tuple(RequirementSocket(name, Protocol.POSTGRES, (binding,)) for name,binding in (
                    ("activity-history-store","CPK_ACTIVITY_HISTORY_DATABASE_URL"),
                    ("graph-topology-store","CPK_GRAPH_TOPOLOGY_DATABASE_URL"),
                    ("observer-state-store","CPK_OBSERVER_STATE_DATABASE_URL"),
                    ("workplace-store","CPK_WORKPLACE_DATABASE_URL"),
                )),
                providers=(ProviderSocket("http-api",Protocol.HTTP),ProviderSocket("mcp",Protocol.MCP_STREAMABLE_HTTP)),
            ),
            provider_ports=(ProviderRuntimePort("http-api",8080),ProviderRuntimePort("mcp",8080)),
            public_environment=tuple(PublicStaticEnvironmentBinding(name,value) for name,value in sorted(environment.items())),
            configuration_artifacts=(artifact,),
            secret_deliveries=(SecretEnvironmentDelivery("PGPASSWORD",SecretReference("secret://control-plane-kit/postgres/password"),SecretUseIntent("postgres.password")),),
            capabilities=(CapabilityName.HEALTH_CHECKABLE,CapabilityName.LOG_READABLE,CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(cpk_control_declaration().surface,),
            verification=VerificationContract(checks=tuple(
                HttpCheck(check_id=kind,provider_socket="http-api",path=f"/health/{kind}",
                          policy=VerificationPolicy(interval_seconds=2,maximum_attempts=10))
                for kind in ("live","ready")
            )),
        )
    except Exception:
        failure = CpkControlConfigurationError("CPK control configuration is invalid")
    raise failure
