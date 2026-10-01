"""Product policy over common integrity-sensitive receiver configuration."""
import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.receiver_configuration import ReceiverNodeControlConfiguration, ReceiverNodeControlConfigurationCodec
from .health_transit_configuration import _public_key, _INPUT_ERRORS

CONTROL_PATH = "/etc/cpk/gateway/control.json"
MAX_CONTROL_BYTES = 65536
PROFILE = "workload-node-control-configuration.v2"
_ERROR = "gateway control configuration is invalid"


class GatewayControlConfigurationError(ValueError):
    """Fixed refusal without candidate material or exception chains."""


def gateway_control_declaration():
    return core.WorkloadNodeControlSurfaceDeclaration(core.WorkloadNodeControlSurfaceDescriptor(
        core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "control"), (),
        health_reads=(core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)),
        profile=core.WorkloadNodeControlSurfaceDeclarationProfile.V2)


def _require_gateway_configuration(configuration):
    if (type(configuration) is not ReceiverNodeControlConfiguration
            or configuration.declaration != gateway_control_declaration()):
        raise ValueError
    # Preserve this receiver's existing canonical Ed25519 key admission policy.
    for family in configuration.verifiers:
        for key in family.public_keys:
            _public_key(key)
    return configuration


def decode_gateway_control_configuration(raw):
    try:
        return _require_gateway_configuration(ReceiverNodeControlConfigurationCodec().decode_bytes(raw))
    except _INPUT_ERRORS:
        failure = GatewayControlConfigurationError(_ERROR)
    raise failure


def gateway_control_configuration_artifact(configuration):
    try:
        content = ReceiverNodeControlConfigurationCodec().encode_bytes(configuration)
        decode_gateway_control_configuration(content)
        return ConfigurationArtifact("gateway-control", CONTROL_PATH, ConfigurationMediaType.JSON,
            content.decode("utf-8"), ConfigurationFileMode.READ_ONLY)
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
        from control_plane_kit_server_sdk.wrapper import load_wrapper_configuration
        return _require_gateway_configuration(load_wrapper_configuration())
    except (OSError, *_INPUT_ERRORS):
        failure = GatewayControlConfigurationError(_ERROR)
    raise failure


def require_matching_gateway_control(control, relay):
    if control.target != relay.gateway_target:
        raise GatewayControlConfigurationError(_ERROR)
