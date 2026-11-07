"""Translate product-owned sample trust into Operations' nominal read model.

The gateway process shares the same product parser without importing Operations.
Missing source dependencies refuse; this module never invents current authority.
"""
from control_plane_kit_core.configuration import (
    ConfigurationArtifactRequirement, ConfigurationMediaType, ConfigurationFileMode,
)
from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.products import (
    ProductDescriptorDocument, ProductDescriptorCodec, ProductReference, product_configuration_slots,
)
from control_plane_kit_core.runtime_management import GatewayTransitProtocol
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import (
    ARTIFACT_ID, CONFIGURATION_PATH, CONFIGURATION_ENVIRONMENT, gateway_http_sample_trust_from_artifact,
)
from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
    ARTIFACT_ID as ROUTES_ARTIFACT_ID, CONFIGURATION_PATH as ROUTES_PATH,
)


class HttpSampleCompositionUnavailable(ValueError):
    """Fixed refusal when an exact supported source composition is unavailable."""


def _operations_types():
    try:
        from control_plane_kit_operations.http_sample_compatibility import (
            GatewayHttpSampleBinding, GatewayHttpSampleTrust,
        )
        return GatewayHttpSampleBinding, GatewayHttpSampleTrust
    except ImportError:
        failure = HttpSampleCompositionUnavailable("HTTP sample composition is unavailable")
    raise failure


class GatewayHttpSampleDecoder:
    def decode(self, artifact):
        """Operations supplies the actual qualified ConfigurationArtifact."""
        _, nominal_trust = _operations_types()
        checked = gateway_http_sample_trust_from_artifact(artifact)
        return nominal_trust(checked.gateway_target,
            DelegationKeyPurpose.GATEWAY_HTTP_VERIFICATION_SAMPLE_TRANSIT,
            checked.issuer, checked.public_keys)


def gateway_http_sample_binding(document):
    """Register exact product/slot semantics, not runtime support or permission."""
    binding_type, _ = _operations_types()
    try:
        if type(document) is not ProductDescriptorDocument:
            raise ValueError
        checked = ProductDescriptorCodec().decode_document(document.content)
        if checked != document:
            raise ValueError
        contract = checked.product.runtime_contract
        slot = ConfigurationArtifactRequirement(ARTIFACT_ID, CONFIGURATION_PATH,
            ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY)
        routes = ConfigurationArtifactRequirement(ROUTES_ARTIFACT_ID, ROUTES_PATH,
            ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY)
        def identity(value):
            return value.artifact_id, value.target_path, value.media_type, value.file_mode
        declared = product_configuration_slots(contract)
        if (any(sum(identity(value) == identity(expected) for value in declared) != 1
                for expected in (slot, routes))
                or sum(value == PublicStaticEnvironmentBinding(CONFIGURATION_ENVIRONMENT, CONFIGURATION_PATH)
                       for value in contract.public_environment) != 1
                or contract.gateway_transit is None
                or contract.gateway_transit.protocol is not GatewayTransitProtocol.RECEIVER_HEALTH_READ_V2):
            raise ValueError
        return binding_type(ProductReference.from_document(checked), slot, GatewayHttpSampleDecoder(), route_slot=routes)
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError, OverflowError):
        failure = HttpSampleCompositionUnavailable("HTTP sample composition is unavailable")
    raise failure
