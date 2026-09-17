"""Pure product parsing for an explicitly selected Operations receiver registry."""
from dataclasses import dataclass, replace

from control_plane_kit_core.configuration import ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.node_control import workload_node_control_audience
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
from .control_configuration import (
    CONTROL_PATH, CpkControlConfigurationError, decode_cpk_control_configuration,
)


_UNAVAILABLE = "health receiver trust is unavailable"
_WORKLOAD_SLOT = ("cpk-control", CONTROL_PATH, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY)
_GATEWAY_SLOT = (ARTIFACT_ID, CONFIGURATION_PATH, ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY)


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
) -> HealthReceiverDecoders:
    """Bind explicitly supplied exact documents; this does not admit product support.

    The caller owns supported-product/input admission. No catalogue lookup,
    default artifact decoding, configuration I/O, clock or authority is implied.
    Empty input returns the existing fail-closed registry.
    """
    if type(workload_documents) is not tuple or type(gateway_documents) is not tuple:
        raise HealthReceiverTrustError(_UNAVAILABLE)
    workloads = tuple(_binding(value, CpkWorkloadHealthReceiverDecoder,
        DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, "cpk-control-configuration.v1", _WORKLOAD_SLOT)
        for value in workload_documents)
    gateways = tuple(_binding(value, GatewayHealthReceiverDecoder,
        DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, PROFILE, _GATEWAY_SLOT)
        for value in gateway_documents)
    return HealthReceiverDecoders(workloads + gateways)
