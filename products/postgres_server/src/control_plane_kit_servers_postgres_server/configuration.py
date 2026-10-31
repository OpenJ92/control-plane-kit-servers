"""PostgreSQL wrapper configuration and source-only runtime contract."""
from __future__ import annotations

from dataclasses import replace

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.lifecycle import ResourceLifecycle
from control_plane_kit_core.products import ProductRuntimeContract, ProviderRuntimePort, RetainedDataMount
from control_plane_kit_core.receiver_configuration import ReceiverNodeControlConfiguration, ReceiverNodeControlConfigurationCodec
from control_plane_kit_core.secrets import (
    SecretFileDelivery, SecretFileMode, SecretFilePathBinding, SecretReference, SecretUseIntent,
)
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import VerificationContract
from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT

CONTROL_PATH = "/etc/cpk/postgres/control.json"
PASSWORD_PATH = "/run/secrets/postgres/password"
PGDATA = "/var/lib/postgresql/data"


class PostgresConfigurationError(ValueError):
    """Closed startup error which never carries configuration material."""


def postgres_control_declaration() -> core.WorkloadNodeControlSurfaceDeclaration:
    return core.WorkloadNodeControlSurfaceDeclaration(
        core.WorkloadNodeControlSurfaceDescriptor(
            core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "management"),
            (), health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS),
        ), profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2,
    )


def _require_configuration(configuration: ReceiverNodeControlConfiguration) -> ReceiverNodeControlConfiguration:
    default = postgres_control_declaration()
    readiness_only = replace(default, surface=replace(default.surface,
        health_reads=(core.NodeHealthReadKind.READINESS,)))
    if (type(configuration) is not ReceiverNodeControlConfiguration
            or configuration.declaration not in (default, readiness_only)):
        raise ValueError
    return configuration


def decode_postgres_control_configuration(raw: bytes) -> ReceiverNodeControlConfiguration:
    try:
        return _require_configuration(ReceiverNodeControlConfigurationCodec().decode_bytes(raw))
    except Exception:
        failure = PostgresConfigurationError("PostgreSQL control configuration is invalid")
    raise failure


def read_postgres_control_configuration() -> ReceiverNodeControlConfiguration:
    try:
        from control_plane_kit_server_sdk.wrapper import load_wrapper_configuration
        return _require_configuration(load_wrapper_configuration())
    except Exception:
        failure = PostgresConfigurationError("PostgreSQL control configuration is invalid")
    raise failure


def postgres_control_configuration_artifact(configuration: ReceiverNodeControlConfiguration) -> ConfigurationArtifact:
    try:
        content = ReceiverNodeControlConfigurationCodec().encode_bytes(configuration)
        decode_postgres_control_configuration(content)
        return ConfigurationArtifact("postgres-control", CONTROL_PATH, ConfigurationMediaType.JSON,
                                     content.decode("utf-8"), ConfigurationFileMode.READ_ONLY)
    except Exception:
        failure = PostgresConfigurationError("PostgreSQL control configuration is invalid")
    raise failure


def postgres_source_runtime_contract(artifact: ConfigurationArtifact) -> ProductRuntimeContract:
    """Describe source composition without changing the historical descriptor."""
    try:
        if (type(artifact) is not ConfigurationArtifact or artifact.artifact_id != "postgres-control"
                or artifact.target_path != CONTROL_PATH or artifact.media_type is not ConfigurationMediaType.JSON
                or artifact.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        configuration = decode_postgres_control_configuration(artifact.content.encode("utf-8"))
        return ProductRuntimeContract(
            sockets=BlockSockets(providers=(ProviderSocket("postgres", Protocol.POSTGRES),
                                            ProviderSocket("management", Protocol.HTTP))),
            provider_ports=(ProviderRuntimePort("postgres", 5432), ProviderRuntimePort("management", 8000)),
            configuration_artifacts=(artifact,),
            public_environment=(
                PublicStaticEnvironmentBinding(WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT, CONTROL_PATH),
                PublicStaticEnvironmentBinding("POSTGRES_DB", "cpk"),
                PublicStaticEnvironmentBinding("POSTGRES_USER", "cpk"),
                PublicStaticEnvironmentBinding("PGDATA", PGDATA),
            ),
            secret_deliveries=(SecretFileDelivery(PASSWORD_PATH,
                SecretReference("secret://control-plane-kit/postgres/password"),
                SecretUseIntent.POSTGRES_PASSWORD, SecretFileMode.OWNER_READ_ONLY,
                SecretFilePathBinding("POSTGRES_PASSWORD_FILE")),),
            retained_data_mounts=(RetainedDataMount("postgres-data", PGDATA),),
            capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(configuration.declaration.surface,), verification=VerificationContract(),
            lifecycle=ResourceLifecycle.owned_with_retained_data("postgres-data"),
        )
    except Exception:
        failure = PostgresConfigurationError("PostgreSQL control configuration is invalid")
    raise failure
