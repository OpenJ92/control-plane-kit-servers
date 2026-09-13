"""Pure product framing over the accepted Secrets receiving protocol."""
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import (
    ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType,
)
from control_plane_kit_core.lifecycle import ResourceLifecycle
from control_plane_kit_core.products import (
    ProductRuntimeContract, ProviderRuntimePort, RetainedDataMount,
)
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import HttpCheck, VerificationContract, VerificationPolicy
from control_plane_kit_secrets.control import (
    SecretsControlConfiguration,
    decode_secrets_control_configuration,
    encode_secrets_control_configuration,
)


CONTROL_PATH = "/etc/cpk/secrets-server/control.json"


class SecretsProductConfigurationError(ValueError):
    def __init__(self) -> None:
        super().__init__("Secrets product control configuration is invalid")


def secrets_control_configuration_artifact(
    configuration: SecretsControlConfiguration,
) -> ConfigurationArtifact:
    try:
        content = encode_secrets_control_configuration(configuration).decode("utf-8")
        return ConfigurationArtifact(
            "secrets-control", CONTROL_PATH, ConfigurationMediaType.JSON,
            content, ConfigurationFileMode.READ_ONLY,
        )
    except Exception:
        failure = SecretsProductConfigurationError()
    raise failure


def secrets_source_runtime_contract(artifact: ConfigurationArtifact) -> ProductRuntimeContract:
    """Source composition only; historical published image contracts stay distinct."""
    try:
        if type(artifact) is not ConfigurationArtifact:
            raise ValueError
        admitted = ConfigurationArtifact.from_descriptor(artifact.descriptor())
        if (admitted.artifact_id != "secrets-control" or admitted.target_path != CONTROL_PATH
                or admitted.media_type is not ConfigurationMediaType.JSON
                or admitted.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        configuration = decode_secrets_control_configuration(admitted.content.encode("utf-8"))
        return ProductRuntimeContract(
            sockets=BlockSockets(providers=(ProviderSocket("control", Protocol.HTTP),)),
            provider_ports=(ProviderRuntimePort("control", 8081),),
            # The fixed path variable is image ENV, not a graph public binding.
            public_environment=(),
            configuration_artifacts=(admitted,),
            secret_deliveries=(),
            retained_data_mounts=(RetainedDataMount("provider-data", "/var/lib/cpk-secrets"),),
            capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(configuration.declaration.surface,),
            verification=VerificationContract(checks=tuple(
                HttpCheck(check_id=kind, provider_socket="control", path="/health/" + kind,
                          expected_statuses=(200,), policy=VerificationPolicy(
                              timeout_seconds=5, interval_seconds=1,
                              maximum_attempts=10, maximum_evidence_bytes=16384,
                          )) for kind in ("live", "ready")
            )),
            lifecycle=ResourceLifecycle.owned_with_retained_data("provider-data"),
        )
    except Exception:
        failure = SecretsProductConfigurationError()
    raise failure
