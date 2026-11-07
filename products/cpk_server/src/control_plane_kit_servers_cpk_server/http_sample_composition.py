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


def http_sample_service_options(registrations):
    """Use the actual Docker registration as both admission/execution evidence."""
    from control_plane_kit_core.types import RuntimeKind
    from control_plane_kit_operations.runtime_adapter_registration import RuntimeAdapterRegistration
    registration = None if registrations is None else registrations.get(RuntimeKind.DOCKER)
    support = getattr(registration, "http_sample_support", None)
    if support is None:
        adapter = getattr(registration, "adapter", registration)
        if getattr(adapter, "http_sample_support", None) is not None:
            raise HttpSampleCompositionUnavailable("HTTP sample composition is unavailable")
        return {}
    try:
        from control_plane_kit_operations.http_sample_execution import HttpSampleExecutionSupport
        if (type(registration) is not RuntimeAdapterRegistration
                or type(support) is not HttpSampleExecutionSupport
                or registration.invocation_profile != "cpk.semantic-invocations.v1"
                or not registration.ordinary_verification_invocations
                or registration.adapter.http_sample_support is not support):
            raise ValueError
        return {"http_sample_support": support, "http_sample_registration": registration}
    except (ImportError, ValueError, TypeError, AttributeError):
        failure = HttpSampleCompositionUnavailable("HTTP sample composition is unavailable")
    raise failure


class _SampleCheckInvocations:
    """Map only the reached owner's result; keep its admission acknowledgements."""
    def __init__(self, original, support):
        self.original, self.support = original, support

    @property
    def control_error(self):
        return self.original.control_error

    def admit(self, kind, *, authorization_id=None):
        return self.original.admit(kind, authorization_id=authorization_id)

    def record_outcome(self, permit, outcome):
        return self.original.record_outcome(permit, outcome)

    def prepare_http_sample(self):
        from control_plane_kit_operations.http_sample_execution import PreparedHttpSampleCheck
        prepared = self.original.prepare_http_sample()
        if (type(prepared) is not PreparedHttpSampleCheck
                or prepared.transit_provider_socket_name != self.support.transit_provider_socket_name):
            raise HttpSampleCompositionUnavailable("HTTP sample composition is unavailable")
        # The ingress is the producer's own per-plan selection, not a second
        # hostname supplied by the API caller or inferred by this wrapper.
        return http_sample_check_input(sender_input=prepared.sender_input, ingress=prepared.ingress,
            gateway_binding=self.support.gateway_binding,
            transit_provider_socket_name=prepared.transit_provider_socket_name)


class _SampleRuntimeInvocations:
    def __init__(self, original, support):
        self.original, self.http_sample_support = original, support

    @property
    def control_error(self):
        return self.original.control_error

    def admit(self, kind, *, authorization_id=None):
        return self.original.admit(kind, authorization_id=authorization_id)

    def record_outcome(self, permit, outcome):
        return self.original.record_outcome(permit, outcome)

    def for_check(self, check_id):
        return _SampleCheckInvocations(self.original.for_check(check_id), self.http_sample_support)

    def acquire_http_sample_route(self):
        from control_plane_kit_operations.http_sample_execution import PreparedHttpSampleRoute
        from control_plane_kit_core.receiver_identity import NodeControlAuthorityContext
        from control_plane_kit_interpreters.probes.http_sample_transport import SelectedHttpSampleGateway
        from control_plane_kit_interpreters.probes.http_sample_check import HttpSampleRouteInput
        acquired = self.original.acquire_http_sample_route()
        support = self.http_sample_support
        if (type(acquired) is not PreparedHttpSampleRoute
                or acquired.transit_provider_socket_name != support.transit_provider_socket_name
                or acquired.compatibility.gateway_product != support.gateway_binding.product):
            raise HttpSampleCompositionUnavailable("HTTP sample composition is unavailable")
        selected = acquired.compatibility
        return HttpSampleRouteInput(SelectedHttpSampleGateway(acquired.ingress,
            selected.gateway_trust.target, selected.route, acquired.transit_provider_socket_name),
            tuple(entry.check for entry in selected.receiver.checks),
            NodeControlAuthorityContext(selected.desired_graph_id, selected.projection_id), selected.workload_product)


class HttpSampleRuntimeAdapter:
    """Product composition only; actual runtime effects stay in Interpreters."""
    def __init__(self, adapter, support):
        if adapter.http_sample_support is not support:
            raise HttpSampleCompositionUnavailable("HTTP sample composition is unavailable")
        self.adapter, self.http_sample_support = adapter, support

    def _invocations(self, original):
        marker = getattr(original, "http_sample_support", None)
        if marker is None:
            return original
        if marker is not self.http_sample_support:
            raise HttpSampleCompositionUnavailable("HTTP sample composition is unavailable")
        return _SampleRuntimeInvocations(original, marker)

    def execute(self, request, *, invocations=None):
        return self.adapter.execute(request, invocations=self._invocations(invocations))

    def execute_with_authority(self, request, authority, *, invocations=None):
        return self.adapter.execute_with_authority(request, authority, invocations=self._invocations(invocations))


def compose_http_sample_runtime(adapter, *, support, resolver, public_resolver, clock):
    """Explicit supported composition, never automatic capability discovery."""
    try:
        from control_plane_kit_operations.http_sample_execution import HttpSampleExecutionSupport
        from control_plane_kit_interpreters.probes.http_sample_check import HttpSampleCheckExecutor
        from control_plane_kit_interpreters.probes.http_sample_transport import SignedGatewayHttpSampleClient
        from dataclasses import replace
        if type(support) is not HttpSampleExecutionSupport:
            raise ValueError
        native = replace(adapter, http_sample_executor=HttpSampleCheckExecutor(resolver,
            SignedGatewayHttpSampleClient(clock=clock, public_resolver=public_resolver), clock, support))
        return HttpSampleRuntimeAdapter(native, support)
    except (ImportError, ValueError, TypeError, AttributeError):
        failure = HttpSampleCompositionUnavailable("HTTP sample composition is unavailable")
    raise failure
