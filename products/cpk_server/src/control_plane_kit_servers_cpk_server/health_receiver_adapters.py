"""Pure product parsing for an explicitly selected Operations receiver registry."""
from dataclasses import dataclass, replace

from control_plane_kit_core.configuration import ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.node_control import NodeHealthReadKind, workload_node_control_audience
from control_plane_kit_core.products import (
    ProductDescriptorCodec, ProductDescriptorDocument, ProductDescriptorError, ProductReference,
)
from control_plane_kit_operations.health_receiver_trust import (
    GatewayHealthReceiverTrust, WorkloadHealthReceiverTrust, HealthReceiverSelection,
    HealthReceiverDecoderBinding, HealthReceiverDecoders, HealthReceiverTrustError,
)
from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import (
    ARTIFACT_ID, CONFIGURATION_PATH, PROFILE, GatewayHealthTransitConfigurationError,
    decode_gateway_health_transit_configuration,
)
from control_plane_kit_servers_cpk_local_gateway.control_configuration import (
    CONTROL_PATH as GATEWAY_CONTROL_PATH, PROFILE as GATEWAY_CONTROL_PROFILE,
    GatewayControlConfigurationError, decode_gateway_control_configuration,
    require_matching_gateway_control,
)
from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
    ARTIFACT_ID as TARGETS_ARTIFACT_ID, CONFIGURATION_PATH as TARGETS_PATH,
    GatewayHealthRelayConfigurationError, GatewayHealthTargetBinding,
    decode_gateway_health_relay_configuration, require_matching_receiver,
)
from .control_configuration import (
    CONTROL_PATH, CpkControlConfigurationError, decode_cpk_control_configuration,
)


_UNAVAILABLE = "health receiver trust is unavailable"
_WORKLOAD_SLOT = ("cpk-control", CONTROL_PATH, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY)
_GATEWAY_SLOT = (ARTIFACT_ID, CONFIGURATION_PATH, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY)
_GATEWAY_SELF_SLOT = ("gateway-control", GATEWAY_CONTROL_PATH, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY)
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


@dataclass(frozen=True, slots=True, repr=False)
class CpkWorkloadHealthReceiverDecoder:
    product_reference: ProductReference

    def decode(self, selection: HealthReceiverSelection) -> WorkloadHealthReceiverTrust:
        raw = _selected_bytes(selection, self.product_reference, _WORKLOAD_SLOT)
        try:
            configured = decode_cpk_control_configuration(raw)
        except CpkControlConfigurationError:
            failure = HealthReceiverTrustError(_UNAVAILABLE)
        else:
            return WorkloadHealthReceiverTrust(
                target=configured.target, runtime_id=configured.runtime_id,
                declaration=configured.declaration, purpose=configured.health_keys.purpose,
                issuer=configured.health_issuer, audience=workload_node_control_audience(configured.target),
                public_keys=configured.health_keys.public_keys,
            )
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
                workspace_id=configured.workspace_id, gateway_node_id=configured.gateway_node_id,
                runtime_id=configured.runtime_id, purpose=configured.purpose, issuer=configured.issuer,
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
    raw = _declared_selected_bytes(selection, _GATEWAY_SELF_SLOT)
    try:
        configured = decode_gateway_control_configuration(raw)
    except GatewayControlConfigurationError:
        failure = HealthReceiverTrustError(_UNAVAILABLE)
    else:
        target = configured.target
        contract = selection.descriptor_document.product.runtime_contract
        own_surfaces = tuple(value for value in contract.control_surfaces
                             if value.provider_socket_name.value == selection.provider_socket_name)
        if ((target.workspace_id.value, target.graph_revision.value, target.node_id.value,
             target.provider_socket_name.value, configured.runtime_id.value) !=
            (selection.workspace_id, selection.authored_graph_id, selection.receiver_node_id,
             selection.provider_socket_name, selection.runtime_id)
                or own_surfaces != (configured.declaration.surface,)
                or NodeHealthReadKind.READINESS not in configured.declaration.surface.health_reads):
            raise HealthReceiverTrustError(_UNAVAILABLE)
        return configured
    raise failure


@dataclass(frozen=True, slots=True, repr=False)
class GatewaySelfHealthReceiverDecoder:
    product_reference: ProductReference

    def decode(self, selection: HealthReceiverSelection) -> WorkloadHealthReceiverTrust:
        _selected_bytes(selection, self.product_reference, _GATEWAY_SELF_SLOT)
        configured = _gateway_self_configuration(selection)
        return WorkloadHealthReceiverTrust(
            target=configured.target, runtime_id=configured.runtime_id,
            declaration=configured.declaration, purpose=configured.health_keys.purpose,
            issuer=configured.health_issuer, audience=workload_node_control_audience(configured.target),
            public_keys=configured.health_keys.public_keys,
        )


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
    if declaration is None or any(value.provider_socket_name != declaration.provider_socket_name
                                  for value in (transit, targets)):
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
                         and value.runtime_id == configured.runtime_id and value.declaration == configured.declaration)
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
    *, workload_documents: tuple[ProductDescriptorDocument, ...] = (),
    gateway_documents: tuple[ProductDescriptorDocument, ...] = (),
    gateway_self_documents: tuple[ProductDescriptorDocument, ...] = (),
) -> HealthReceiverDecoders:
    """Bind explicitly supplied exact documents; this does not admit product support.

    The caller owns supported-product/input admission. No catalogue lookup,
    default artifact decoding, configuration I/O, clock or authority is implied.
    Empty input returns the existing fail-closed registry.
    """
    if any(type(value) is not tuple for value in (workload_documents, gateway_documents, gateway_self_documents)):
        raise HealthReceiverTrustError(_UNAVAILABLE)
    workloads = tuple(_binding(value, CpkWorkloadHealthReceiverDecoder,
        DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, "cpk-control-configuration.v1", _WORKLOAD_SLOT)
        for value in workload_documents)
    gateways = tuple(_binding(value, GatewayHealthReceiverDecoder,
        DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, PROFILE, _GATEWAY_SLOT)
        for value in gateway_documents)
    gateway_selves = tuple(_binding(value, GatewaySelfHealthReceiverDecoder,
        DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, GATEWAY_CONTROL_PROFILE, _GATEWAY_SELF_SLOT)
        for value in gateway_self_documents)
    return HealthReceiverDecoders(workloads + gateways + gateway_selves)
