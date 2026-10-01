"""Pure common receiver selection and separate product-owned transit parsing."""
from dataclasses import dataclass, replace

from control_plane_kit_core.configuration import ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.node_control import NodeHealthReadKind
from control_plane_kit_core.products import (
    ProductDescriptorCodec, ProductDescriptorDocument, ProductDescriptorError, ProductReference,
)
from control_plane_kit_operations.health_receiver_trust import (
    GatewayHealthReceiverTrust, HealthReceiverSelection,
    HealthReceiverDecoderBinding, HealthReceiverDecoders, HealthReceiverTrustError,
)
from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import (
    ARTIFACT_ID, CONFIGURATION_PATH, PROFILE, GatewayHealthTransitConfigurationError,
    decode_gateway_health_transit_configuration,
)
from control_plane_kit_servers_cpk_local_gateway.control_configuration import (
    GatewayControlConfigurationError,
    require_matching_gateway_control,
)
from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
    ARTIFACT_ID as TARGETS_ARTIFACT_ID, CONFIGURATION_PATH as TARGETS_PATH,
    GatewayHealthRelayConfigurationError, GatewayHealthTargetBinding,
    decode_gateway_health_relay_configuration, require_matching_receiver,
)
from control_plane_kit_core.receiver_configuration import (
    ReceiverNodeControlConfiguration, ReceiverNodeControlConfigurationCodec,
    select_receiver_node_control_configuration_artifact,
)
from control_plane_kit_core.wrapper_configuration import WrapperConfigurationError
from control_plane_kit_core.runtime_management import GatewayTransitProtocol


_UNAVAILABLE = "health receiver trust is unavailable"
_GATEWAY_SLOT = (ARTIFACT_ID, CONFIGURATION_PATH, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY)
_TARGETS_SLOT = (TARGETS_ARTIFACT_ID, TARGETS_PATH, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY)


def _slot(artifact):
    return artifact.artifact_id, artifact.target_path, artifact.media_type, artifact.file_mode


def _selected_bytes(selection, reference, slot):
    if type(selection) is not HealthReceiverSelection:
        raise HealthReceiverTrustError(_UNAVAILABLE)
    # Revalidate canonical provenance and artifact integrity even for direct
    # adapter calls. Operations independently owns original graph selection.
    checked = replace(selection)
    if checked.product_reference != reference or _slot(checked.artifact) != slot:
        raise HealthReceiverTrustError(_UNAVAILABLE)
    return checked.artifact.content.encode("utf-8")


def select_own_health_configuration(selection: HealthReceiverSelection) -> ReceiverNodeControlConfiguration:
    """Select original public bytes; this does not prove current caller authority."""
    if type(selection) is not HealthReceiverSelection:
        raise HealthReceiverTrustError(_UNAVAILABLE)
    checked = replace(selection)
    contract = checked.descriptor_document.product.runtime_contract
    try:
        declared = select_receiver_node_control_configuration_artifact(
            artifacts=contract.configuration_artifacts, environment=contract.public_environment,
            control_surfaces=contract.control_surfaces)
        if _slot(declared) != _slot(checked.artifact):
            raise HealthReceiverTrustError(_UNAVAILABLE)
        actual = select_receiver_node_control_configuration_artifact(
            artifacts=(checked.artifact,), environment=contract.public_environment,
            control_surfaces=contract.control_surfaces)
        configured = ReceiverNodeControlConfigurationCodec().decode_bytes(actual.content.encode("utf-8"))
    except WrapperConfigurationError:
        failure = HealthReceiverTrustError(_UNAVAILABLE)
    else:
        target = configured.target
        if ((target.workspace_id.value, target.runtime_id.value, target.node_id.value,
             target.provider_socket_name.value) !=
                (checked.workspace_id, checked.runtime_id, checked.receiver_node_id, checked.provider_socket_name)):
            raise HealthReceiverTrustError(_UNAVAILABLE)
        return configured
    raise failure


@dataclass(frozen=True, slots=True, repr=False)
class GatewayHealthReceiverDecoder:
    product_reference: ProductReference

    def decode(self, selection: HealthReceiverSelection) -> GatewayHealthReceiverTrust:
        raw = _selected_bytes(selection, self.product_reference, _GATEWAY_SLOT)
        try:
            configured = decode_gateway_health_transit_configuration(raw)
        except GatewayHealthTransitConfigurationError:
            failure = HealthReceiverTrustError(_UNAVAILABLE)
        else:
            return GatewayHealthReceiverTrust(
                workspace_id=configured.gateway_target.workspace_id, gateway_node_id=configured.gateway_target.node_id,
                runtime_id=configured.gateway_target.runtime_id, purpose=configured.purpose, issuer=configured.issuer,
                audience=configured.audience, public_keys=configured.public_keys,
            )
        raise failure


def _declared_selected_bytes(selection, slot):
    if type(selection) is not HealthReceiverSelection:
        raise HealthReceiverTrustError(_UNAVAILABLE)
    raw = _selected_bytes(selection, selection.product_reference, slot)
    declared = tuple(value for value in selection.descriptor_document.product.runtime_contract.configuration_artifacts
                     if _slot(value) == slot)
    if len(declared) != 1:
        raise HealthReceiverTrustError(_UNAVAILABLE)
    return raw


def _gateway_self_configuration(selection):
    configured = select_own_health_configuration(selection)
    if NodeHealthReadKind.READINESS not in configured.declaration.surface.health_reads:
        raise HealthReceiverTrustError(_UNAVAILABLE)
    return configured


def select_gateway_self_health_binding(
    *, transit: HealthReceiverSelection, targets: HealthReceiverSelection,
    control: HealthReceiverSelection,
) -> GatewayHealthTargetBinding:
    """Return selected internal relay material, never authority or installed-state proof."""
    transit_raw = _declared_selected_bytes(transit, _GATEWAY_SLOT)
    targets_raw = _declared_selected_bytes(targets, _TARGETS_SLOT)
    configured = _gateway_self_configuration(control)
    context_fields = ("workspace_id", "authored_graph_id", "realized_projection_id", "graph_side",
                      "receiver_node_id", "runtime_id", "product_reference", "descriptor_document")
    if any(getattr(value, field) != getattr(control, field)
           for value in (transit, targets) for field in context_fields):
        raise HealthReceiverTrustError(_UNAVAILABLE)
    declaration = control.descriptor_document.product.runtime_contract.gateway_transit
    if (declaration is None or declaration.protocol is not GatewayTransitProtocol.RECEIVER_HEALTH_READ_V2
            or any(value.provider_socket_name != declaration.provider_socket_name for value in (transit, targets))):
        raise HealthReceiverTrustError(_UNAVAILABLE)
    try:
        trust = decode_gateway_health_transit_configuration(transit_raw)
        relay = decode_gateway_health_relay_configuration(targets_raw)
        require_matching_receiver(trust, relay)
        require_matching_gateway_control(configured, relay)
    except (GatewayHealthTransitConfigurationError, GatewayHealthRelayConfigurationError, GatewayControlConfigurationError):
        failure = HealthReceiverTrustError(_UNAVAILABLE)
    else:
        bindings = tuple(value for value in relay.targets if value.target == configured.target
                         and value.declaration == configured.declaration)
        if len(bindings) != 1:
            raise HealthReceiverTrustError(_UNAVAILABLE)
        return bindings[0]
    raise failure


def _binding(document, decoder_type, purpose, profile, slot):
    if type(document) is not ProductDescriptorDocument:
        raise HealthReceiverTrustError(_UNAVAILABLE)
    try:
        canonical = ProductDescriptorCodec().decode_document(document.content)
    except ProductDescriptorError:
        failure = HealthReceiverTrustError(_UNAVAILABLE)
    else:
        if canonical != document:
            raise HealthReceiverTrustError(_UNAVAILABLE)
        declared = tuple(value for value in canonical.product.runtime_contract.configuration_artifacts
                         if _slot(value) == slot)
        if len(declared) != 1:
            raise HealthReceiverTrustError(_UNAVAILABLE)
        reference = ProductReference.from_document(canonical)
        return HealthReceiverDecoderBinding(reference, purpose, profile, *slot, decoder_type(reference))
    raise failure


def health_receiver_decoders(
    *, gateway_documents: tuple[ProductDescriptorDocument, ...] = (),
) -> HealthReceiverDecoders:
    """Bind exact transit documents; common own receivers need no registry.

    The caller owns product admission. No catalogue lookup, file access, clock,
    default-key selection or current authority is implied.
    """
    if type(gateway_documents) is not tuple:
        raise HealthReceiverTrustError(_UNAVAILABLE)
    return HealthReceiverDecoders(tuple(_binding(value, GatewayHealthReceiverDecoder,
        DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, PROFILE, _GATEWAY_SLOT)
        for value in gateway_documents))
