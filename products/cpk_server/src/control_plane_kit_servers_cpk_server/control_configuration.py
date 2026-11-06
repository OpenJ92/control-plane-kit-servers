"""CPK's public, integrity-sensitive configuration and source contract."""
from __future__ import annotations

from enum import StrEnum
import os

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket, RequirementSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationArtifactRequirement, ConfigurationMediaType, ConfigurationFileMode
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.secrets import SecretEnvironmentDelivery, SecretReference, SecretUseIntent
from control_plane_kit_core.products import ProductRuntimeContract, ProviderRuntimePort
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import VerificationContract, VerificationPolicy, HttpCheck
from control_plane_kit_core.receiver_configuration import (
    ReceiverNodeControlConfiguration, ReceiverNodeControlConfigurationCodec,
)
from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT
from control_plane_kit_core.http_verification_sample_installation import (
    HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT,
    HttpVerificationSampleReceiverBinding, HttpVerificationSampleReceiverConfigurationCodec,
    select_http_verification_sample_configuration_slot,
)

CONTROL_PATH = "/etc/cpk/cpk-server/control.json"
MAX_CONTROL_BYTES = 65_536
HTTP_SAMPLE_SLOT = ConfigurationArtifactRequirement("cpk-http-samples",
    "/etc/cpk/cpk-server/http-samples.json", ConfigurationMediaType.JSON,
    ConfigurationFileMode.READ_ONLY)
_PROVIDERS = (ProviderSocket("http-api", Protocol.HTTP), ProviderSocket("mcp", Protocol.MCP_STREAMABLE_HTTP))
_PORTS = (ProviderRuntimePort("http-api", 8080), ProviderRuntimePort("mcp", 8080))


def _verification() -> VerificationContract:
    return VerificationContract(checks=tuple(
        HttpCheck(check_id=kind, provider_socket="http-api", path=f"/health/{kind}",
                  policy=VerificationPolicy(interval_seconds=2, maximum_attempts=10))
        for kind in ("live", "ready")))


def cpk_http_sample_binding(control, configuration) -> HttpVerificationSampleReceiverBinding:
    """Join public sample trust to the independent original CPK contract."""
    try:
        _require_cpk_configuration(control)
        return HttpVerificationSampleReceiverBinding(configuration, control, _verification(), _PROVIDERS, _PORTS)
    except Exception:
        failure = CpkControlConfigurationError("CPK control configuration is invalid")
    raise failure


def cpk_http_sample_configuration_artifact(control, configuration) -> ConfigurationArtifact:
    cpk_http_sample_binding(control, configuration)
    content = HttpVerificationSampleReceiverConfigurationCodec().encode_canonical_bytes(configuration)
    return ConfigurationArtifact(HTTP_SAMPLE_SLOT.artifact_id, HTTP_SAMPLE_SLOT.target_path,
        HTTP_SAMPLE_SLOT.media_type, content.decode("utf-8"), HTTP_SAMPLE_SLOT.file_mode)


def read_cpk_http_sample_binding(control) -> HttpVerificationSampleReceiverBinding | None:
    try:
        if HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT not in os.environ:
            return None
        from control_plane_kit_server_sdk.wrapper import load_http_verification_sample_configuration
        return cpk_http_sample_binding(control, load_http_verification_sample_configuration())
    except Exception:
        failure = CpkControlConfigurationError("CPK control configuration is invalid")
    raise failure


class CpkControlConfigurationError(ValueError):
    """Malformed CPK startup configuration; never carries source material."""


def cpk_control_declaration() -> core.WorkloadNodeControlSurfaceDeclaration:
    return core.WorkloadNodeControlSurfaceDeclaration(
        core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "http-api"),
            (), health_reads=(core.NodeHealthReadKind.LIVENESS,),
        ), profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
    )


def _require_cpk_configuration(configuration: ReceiverNodeControlConfiguration) -> ReceiverNodeControlConfiguration:
    if (type(configuration) is not ReceiverNodeControlConfiguration
            or configuration.declaration != cpk_control_declaration()):
        raise ValueError
    return configuration


def decode_cpk_control_configuration(raw: bytes) -> ReceiverNodeControlConfiguration:
    """Decode common receiving values and enforce this product's declaration."""
    try:
        return _require_cpk_configuration(ReceiverNodeControlConfigurationCodec().decode_bytes(raw))
    except Exception:
        failure = CpkControlConfigurationError("CPK control configuration is invalid")
    raise failure


def read_cpk_control_configuration() -> ReceiverNodeControlConfiguration:
    try:
        from control_plane_kit_server_sdk.wrapper import load_wrapper_configuration
        return _require_cpk_configuration(load_wrapper_configuration())
    except Exception:
        failure = CpkControlConfigurationError("CPK control configuration is invalid")
    raise failure


def cpk_control_configuration_artifact(config: ReceiverNodeControlConfiguration) -> ConfigurationArtifact:
    try:
        content = ReceiverNodeControlConfigurationCodec().encode_bytes(config)
        decode_cpk_control_configuration(content)
        return ConfigurationArtifact("cpk-control", CONTROL_PATH, ConfigurationMediaType.JSON,
                                     content.decode("utf-8"), ConfigurationFileMode.READ_ONLY)
    except Exception:
        failure = CpkControlConfigurationError("CPK control configuration is invalid")
    raise failure


class CpkSourceVariant(StrEnum):
    CPK = "cpk-server"
    DOCKER = "cpk-server-docker"
    DOCKER_CLOUDFLARE = "cpk-server-docker-cloudflare"


def cpk_source_runtime_contract(
    variant: CpkSourceVariant, artifact: ConfigurationArtifact,
    *, sample_artifact: ConfigurationArtifact | None = None,
) -> ProductRuntimeContract:
    """Required source receiver for each variant; historical images stay separate."""
    try:
        if (type(variant) is not CpkSourceVariant or type(artifact) is not ConfigurationArtifact
                or artifact.artifact_id != "cpk-control" or artifact.target_path != CONTROL_PATH
                or artifact.media_type is not ConfigurationMediaType.JSON
                or artifact.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        control = decode_cpk_control_configuration(artifact.content.encode("utf-8"))
        environment = {
            WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT: CONTROL_PATH,
            "CPK_CONTROL_AUTH_CONFIGURED":"true", "CPK_PORT":"8080",
            "CPK_SERVER_MODE":"execution-capable",
            "CPK_RUNTIME_INTERPRETERS":"none" if variant is CpkSourceVariant.CPK else "docker",
            "CPK_INGRESS_INTERPRETERS":"cloudflare" if variant is CpkSourceVariant.DOCKER_CLOUDFLARE else "none",
        }
        if variant is not CpkSourceVariant.CPK:
            environment["CPK_PRODUCT_MATERIAL_RESOLVER"] = "provider"
        artifacts = (artifact,) if sample_artifact is None else (artifact, sample_artifact)
        if sample_artifact is not None:
            environment[HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT] = HTTP_SAMPLE_SLOT.target_path
        public_environment = tuple(PublicStaticEnvironmentBinding(name, value) for name, value in sorted(environment.items()))
        selected = select_http_verification_sample_configuration_slot(expected_slot=HTTP_SAMPLE_SLOT,
            artifacts=artifacts, environment=public_environment)
        if selected is not None:
            samples = HttpVerificationSampleReceiverConfigurationCodec().decode_canonical_bytes(selected.content.encode("utf-8"))
            cpk_http_sample_binding(control, samples)
        return ProductRuntimeContract(
            sockets=BlockSockets(
                requirements=tuple(RequirementSocket(name, Protocol.POSTGRES, (binding,)) for name,binding in (
                    ("activity-history-store","CPK_ACTIVITY_HISTORY_DATABASE_URL"),
                    ("graph-topology-store","CPK_GRAPH_TOPOLOGY_DATABASE_URL"),
                    ("observer-state-store","CPK_OBSERVER_STATE_DATABASE_URL"),
                    ("workplace-store","CPK_WORKPLACE_DATABASE_URL"),
                )),
                providers=_PROVIDERS,
            ),
            provider_ports=_PORTS,
            public_environment=public_environment,
            configuration_artifacts=artifacts,
            secret_deliveries=(SecretEnvironmentDelivery("PGPASSWORD",SecretReference("secret://control-plane-kit/postgres/password"),SecretUseIntent("postgres.password")),),
            capabilities=(CapabilityName.HEALTH_CHECKABLE,CapabilityName.LOG_READABLE,CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(cpk_control_declaration().surface,),
            verification=_verification(),
        )
    except Exception:
        failure = CpkControlConfigurationError("CPK control configuration is invalid")
    raise failure
