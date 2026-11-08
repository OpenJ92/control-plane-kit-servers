"""Translate real Operations prepared SQL values into Core-only native inputs.

No graph lookup, authority grant, provider access or durable mutation lives here.
The normal owner prepares and validates each nominal value before translation.
"""
from .http_sample_composition import (HttpSampleCompositionUnavailable, HttpSampleRuntimeAdapter,
    _SampleCheckInvocations, _SampleRuntimeInvocations, compose_http_sample_runtime)


def native_verification_executors(registration, plan, pair):
    """Static translation selection only; normal Operations still admits it."""
    from control_plane_kit_core.types import RuntimeKind
    from .http_sample_composition import http_sample_service_options
    options = http_sample_service_options({RuntimeKind.DOCKER: registration})
    if not options:
        return {}
    if "managed_verification_support" in options:
        from control_plane_kit_core.planning import compile_managed_verification_bootstrap_activity_plan
        canonical = compile_managed_verification_bootstrap_activity_plan(*pair)
        executors = dict(http_sample_executor=registration.adapter.http_sample_executor,
            postgres_readiness_executor=registration.adapter.postgres_readiness_executor)
    else:
        from control_plane_kit_core.planning import compile_http_sample_bootstrap_activity_plan
        canonical = compile_http_sample_bootstrap_activity_plan(*pair)
        executors = dict(http_sample_executor=registration.adapter.http_sample_executor)
    return executors if plan == canonical and canonical.ready_for_execution else {}


def postgres_readiness_route_input(route, support):
    from control_plane_kit_operations.managed_verification_execution import (
        PreparedPostgresReadinessRoute, ManagedVerificationExecutionSupport,
    )
    from control_plane_kit_core.receiver_identity import NodeControlAuthorityContext
    from control_plane_kit_core.runtime_management import GatewayTransitProtocol
    from control_plane_kit_interpreters.probes.health_transport import SelectedManagementGateway
    from control_plane_kit_interpreters.probes.postgres_readiness_check import PostgresReadinessRouteInput
    if type(route) is not PreparedPostgresReadinessRoute or type(support) is not ManagedVerificationExecutionSupport:
        raise HttpSampleCompositionUnavailable("managed verification composition is unavailable")
    route.__post_init__()
    if (route.selection.product_reference != support.http_samples.gateway_binding.product
            or route.transit_provider_socket_name != support.http_samples.transit_provider_socket_name):
        raise HttpSampleCompositionUnavailable("managed verification composition is unavailable")
    gateway = route.gateway_target
    destination = SelectedManagementGateway(route.ingress, gateway.node_id, route.transit_provider_socket_name,
        gateway.runtime_id, route.binding.target_id, GatewayTransitProtocol.RECEIVER_HEALTH_READ_V2)
    return PostgresReadinessRouteInput(NodeControlAuthorityContext(route.selection.authored_graph_id,
        route.selection.realized_projection_id), route.receiver, destination, route.binding,
        route.selection.descriptor_document, route.selection.artifact, route.transit_selection.artifact)


def postgres_readiness_check_input(prepared, support):
    from control_plane_kit_operations.managed_verification_execution import PreparedPostgresReadinessCheck
    from control_plane_kit_interpreters.probes.health_signing import HealthSigningContext, HealthSigningKey
    from control_plane_kit_interpreters.probes.postgres_readiness_check import PostgresReadinessCheckInput
    if type(prepared) is not PreparedPostgresReadinessCheck:
        raise HttpSampleCompositionUnavailable("managed verification composition is unavailable")
    prepared.__post_init__()
    route = postgres_readiness_route_input(prepared.route, support)
    if support.observer_for(prepared.binding.observer.product) != prepared.binding.observer:
        raise HttpSampleCompositionUnavailable("managed verification composition is unavailable")
    context = HealthSigningContext(prepared.binding.request(), prepared.transit_grant.attempt_id,
        prepared.route.gateway_target, prepared.binding.receiver.declaration,
        prepared.transit_grant.issuer, prepared.workload_grant.issuer)
    return PostgresReadinessCheckInput(prepared.binding, prepared.password_grant, context,
        HealthSigningKey(prepared.transit.public_key, prepared.transit.resolution_grant),
        HealthSigningKey(prepared.workload.public_key, prepared.workload.resolution_grant),
        prepared.transit_grant, prepared.workload_grant, route.destination, route.route,
        route.gateway_product, route.gateway_route_artifact, route.gateway_transit_artifact)


class _ManagedCheckInvocations(_SampleCheckInvocations):
    def __init__(self, original, support):
        super().__init__(original, support.http_samples)
        self.managed_support = support

    def prepare_postgres_readiness(self):
        return postgres_readiness_check_input(self.original.prepare_postgres_readiness(), self.managed_support)


class _ManagedRuntimeInvocations(_SampleRuntimeInvocations):
    def __init__(self, original, support):
        super().__init__(original, support.http_samples)
        self.managed_verification_support = support

    def for_check(self, check_id):
        return _ManagedCheckInvocations(self.original.for_check(check_id), self.managed_verification_support)

    def acquire_managed_verification_route(self):
        return postgres_readiness_route_input(self.original.acquire_managed_verification_route(),
            self.managed_verification_support)


class ManagedVerificationRuntimeAdapter(HttpSampleRuntimeAdapter):
    @property
    def managed_verification_support(self):
        return self.adapter.managed_verification_support

    @property
    def postgres_readiness_executor(self):
        return self.adapter.postgres_readiness_executor

    def _invocations(self, original):
        support = getattr(original, "managed_verification_support", None)
        if support is None:
            return super()._invocations(original)
        samples = getattr(original, "http_sample_support", None)
        if (support is not self.managed_verification_support
                or (samples is not None and samples is not support.http_samples)):
            raise HttpSampleCompositionUnavailable("managed verification composition is unavailable")
        return _ManagedRuntimeInvocations(original, support)


def compose_managed_verification_runtime(adapter, *, support, resolver, public_resolver, clock_epoch_ms):
    from dataclasses import replace
    from control_plane_kit_operations.managed_verification_execution import ManagedVerificationExecutionSupport
    from control_plane_kit_interpreters.probes.health_signing import Ed25519HealthCredentialPairSigner
    from control_plane_kit_interpreters.probes.health_transport import SignedGatewayHealthClient
    from control_plane_kit_interpreters.probes.postgres_readiness_check import PostgresReadinessCheckExecutor
    if type(support) is not ManagedVerificationExecutionSupport or not callable(clock_epoch_ms):
        raise HttpSampleCompositionUnavailable("managed verification composition is unavailable")
    support.__post_init__()
    clock = lambda: clock_epoch_ms() // 1000
    samples = compose_http_sample_runtime(adapter, support=support.http_samples,
        resolver=resolver, public_resolver=public_resolver, clock=clock)
    native = replace(samples.adapter, postgres_readiness_executor=PostgresReadinessCheckExecutor(
        resolver, Ed25519HealthCredentialPairSigner(resolver, clock),
        SignedGatewayHealthClient(clock=clock, public_resolver=public_resolver), clock_epoch_ms, support))
    return ManagedVerificationRuntimeAdapter(native, support.http_samples)
