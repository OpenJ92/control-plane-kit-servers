"""Pure product framing over the accepted Secrets receiving protocol."""
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import (
    ConfigurationArtifact, ConfigurationArtifactRequirement, ConfigurationFileMode, ConfigurationMediaType,
)
from control_plane_kit_core.receiver_configuration import ReceiverNodeControlConfiguration
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT
from control_plane_kit_core.lifecycle import ResourceLifecycle
from control_plane_kit_core.products import (
    ProductRuntimeContract, ProviderRuntimePort, RetainedDataMount,
)
from control_plane_kit_core.types import Protocol
from control_plane_kit_core.verification import HttpCheck, VerificationContract, VerificationPolicy
from control_plane_kit_core.http_verification_sample_installation import (
    HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT,
    HttpVerificationSampleReceiverBinding, HttpVerificationSampleReceiverConfigurationCodec,
    select_http_verification_sample_configuration_slot,
)
from control_plane_kit_secrets.control import (
    decode_secrets_control_configuration,
    encode_secrets_control_configuration,
)


CONTROL_PATH = "/etc/cpk/secrets-server/control.json"
HTTP_SAMPLE_SLOT = ConfigurationArtifactRequirement("secrets-http-samples",
    "/etc/cpk/secrets-server/http-samples.json", ConfigurationMediaType.JSON,
    ConfigurationFileMode.READ_ONLY)
_PROVIDERS = (ProviderSocket("control", Protocol.HTTP),)
_PORTS = (ProviderRuntimePort("control", 8081),)


def _verification() -> VerificationContract:
    return VerificationContract(checks=tuple(
        HttpCheck(check_id=kind, provider_socket="control", path="/health/" + kind,
            expected_statuses=(200,), policy=VerificationPolicy(timeout_seconds=5,
                interval_seconds=1, maximum_attempts=10, maximum_evidence_bytes=16384))
        for kind in ("live", "ready")))


def secrets_http_sample_binding(control, configuration) -> HttpVerificationSampleReceiverBinding:
    """Bind independently loaded Secrets control to original product metadata."""
    try:
        # The service owns the V2 declaration and its receiving validation.
        from control_plane_kit_secrets.control import require_secrets_control_configuration
        require_secrets_control_configuration(control)
        return HttpVerificationSampleReceiverBinding(configuration, control, _verification(), _PROVIDERS, _PORTS)
    except Exception:
        failure = SecretsProductConfigurationError()
    raise failure


def secrets_http_sample_configuration_artifact(control, configuration) -> ConfigurationArtifact:
    secrets_http_sample_binding(control, configuration)
    content = HttpVerificationSampleReceiverConfigurationCodec().encode_canonical_bytes(configuration)
    return ConfigurationArtifact(HTTP_SAMPLE_SLOT.artifact_id, HTTP_SAMPLE_SLOT.target_path,
        HTTP_SAMPLE_SLOT.media_type, content.decode("utf-8"), HTTP_SAMPLE_SLOT.file_mode)


class SecretsProductConfigurationError(ValueError):
    def __init__(self) -> None:
        super().__init__("Secrets product control configuration is invalid")


def secrets_control_configuration_artifact(
    configuration: ReceiverNodeControlConfiguration,
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


def secrets_source_runtime_contract(artifact: ConfigurationArtifact, *,
        sample_artifact: ConfigurationArtifact | None = None) -> ProductRuntimeContract:
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
        artifacts = (admitted,) if sample_artifact is None else (admitted, sample_artifact)
        environment = (PublicStaticEnvironmentBinding(WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT, CONTROL_PATH),)
        if sample_artifact is not None:
            environment += (PublicStaticEnvironmentBinding(
                HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT, HTTP_SAMPLE_SLOT.target_path),)
        selected = select_http_verification_sample_configuration_slot(expected_slot=HTTP_SAMPLE_SLOT,
            artifacts=artifacts, environment=environment)
        if selected is not None:
            samples = HttpVerificationSampleReceiverConfigurationCodec().decode_canonical_bytes(selected.content.encode("utf-8"))
            secrets_http_sample_binding(configuration, samples)
        return ProductRuntimeContract(
            sockets=BlockSockets(providers=_PROVIDERS),
            provider_ports=_PORTS,
            public_environment=environment,
            configuration_artifacts=artifacts,
            secret_deliveries=(),
            retained_data_mounts=(RetainedDataMount("provider-data", "/var/lib/cpk-secrets"),),
            capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(configuration.declaration.surface,),
            verification=_verification(),
            lifecycle=ResourceLifecycle.owned_with_retained_data("provider-data"),
        )
    except Exception:
        failure = SecretsProductConfigurationError()
    raise failure
