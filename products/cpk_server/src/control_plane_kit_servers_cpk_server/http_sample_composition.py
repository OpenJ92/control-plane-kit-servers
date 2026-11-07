"""Translate product-owned sample trust into Operations' nominal read model.

The gateway process shares the same product parser without importing Operations.
Missing source dependencies refuse; this module never invents current authority.
"""
from uuid import uuid4

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


def http_sample_check_input(*, sender_input, ingress, gateway_binding, transit_provider_socket_name):
    """Translate the reached owner's committed references; no stores or effects.

    Its caller supplies the exact admitted per-plan ingress and registered
    support. The interpreter independently compares the resulting Core request
    with the actual effect before resolving either role.
    """
    try:
        from control_plane_kit_operations.http_sample_sender_input import HttpSampleSenderInput
        from control_plane_kit_core.http_verification_samples import (
            HttpVerificationSampleRequest, http_verification_check_digest,
        )
        from control_plane_kit_core.receiver_identity import NodeControlAuthorityContext
        from control_plane_kit_core.public_ingress import NamedPublicIngress, NamedPublicIngressCodec
        from control_plane_kit_interpreters.probes.http_sample_check import (
            HttpSampleCheckInput, HttpSampleSigningKey,
        )
        from control_plane_kit_interpreters.probes.http_sample_transport import SelectedHttpSampleGateway
        binding_type, _ = _operations_types()
        if (type(sender_input) is not HttpSampleSenderInput or type(gateway_binding) is not binding_type
                or type(ingress) is not NamedPublicIngress
                or NamedPublicIngressCodec().decode(ingress.descriptor()) != ingress):
            raise ValueError
        value = sender_input
        selected = value.compatibility
        if (selected.gateway_product != gateway_binding.product
                or ingress.target.node_id != selected.gateway_trust.target.node_id.value
                or ingress.target.provider_socket != transit_provider_socket_name):
            raise ValueError
        request = HttpVerificationSampleRequest(target=selected.receiver.configuration.target,
            authority_context=NodeControlAuthorityContext(selected.desired_graph_id, selected.projection_id),
            declaration_identity=selected.receiver.configuration.declaration_identity,
            gateway_target=selected.gateway_trust.target, route_id=selected.route.target_id,
            run_id=value.attempt.run_id.value, activity_id=value.attempt.activity_id,
            outer_attempt=value.attempt.attempt, effect_id=value.effect_id,
            request_fingerprint=value.request_fingerprint, check_id=value.check.check_id,
            check_digest=http_verification_check_digest(value.check), sample_ordinal=1, request_id=uuid4().hex)
        destination = SelectedHttpSampleGateway(ingress, selected.gateway_trust.target, selected.route,
                                               transit_provider_socket_name)
        return HttpSampleCheckInput(request, value.check, destination,
            HttpSampleSigningKey(value.transit_key.issuer, value.transit_key.public_key, value.transit_grant),
            HttpSampleSigningKey(value.workload_key.issuer, value.workload_key.public_key, value.workload_grant))
    except (ImportError, ValueError, TypeError, AttributeError, KeyError, RecursionError, OverflowError):
        failure = HttpSampleCompositionUnavailable("HTTP sample composition is unavailable")
    raise failure
