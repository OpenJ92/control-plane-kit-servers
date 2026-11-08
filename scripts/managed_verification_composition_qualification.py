"""Nominal owner-to-native composition laws; no current authority or SQL claim."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from control_plane_kit_interpreters.docker.runtime import DockerRuntimeInterpreter
from control_plane_kit_operations.runtime_adapter_registration import RuntimeAdapterRegistration
from control_plane_kit_servers_cpk_server.http_sample_composition import http_sample_service_options, HttpSampleCompositionUnavailable
from control_plane_kit_servers_cpk_server.managed_verification_composition import (
    compose_managed_verification_runtime, postgres_readiness_check_input, postgres_readiness_route_input,
)
from tests.test_managed_verification_execution import ManagedVerificationRouteTests


class ManagedCompositionTests(unittest.TestCase):
    def setUp(self):
        # Reuse the owner's exact supplied-record fixture, not a copied state
        # machine. It explicitly establishes no current admission or dispatch.
        owner = ManagedVerificationRouteTests()
        self.prepared = owner.prepared()
        _, support = owner.inputs()
        self.support = replace(support, postgres_observers=(self.prepared.binding.observer,))

    def test_actual_nominal_route_and_check_preserve_selected_values(self):
        prepared, support = self.prepared, self.support
        route = postgres_readiness_route_input(prepared.route, support)
        value = postgres_readiness_check_input(prepared, support)
        self.assertIs(value.binding, prepared.binding)
        self.assertIs(value.password_grant, prepared.password_grant)
        self.assertIs(value.transit_key.resolution_grant, prepared.transit.resolution_grant)
        self.assertIs(value.workload_key.resolution_grant, prepared.workload.resolution_grant)
        self.assertEqual(value.signing_context.request, prepared.binding.request())
        self.assertEqual(value.destination, route.destination)
        self.assertIs(value.gateway_route_artifact, prepared.route.selection.artifact)
        self.assertIs(value.gateway_transit_artifact, prepared.route.transit_selection.artifact)
        self.assertIs(value.gateway_product, prepared.route.selection.descriptor_document)

    def test_real_native_registration_supplies_same_objects_to_service_options(self):
        def forbidden(*_):
            raise AssertionError("nominal composition must not resolve or dispatch")
        resolver = SimpleNamespace(resolve=forbidden)
        native = compose_managed_verification_runtime(DockerRuntimeInterpreter(client=SimpleNamespace()),
            support=self.support, resolver=resolver, public_resolver=None,
            clock_epoch_ms=lambda:self.prepared.binding.started_at_epoch_ms)
        registration = RuntimeAdapterRegistration(native, invocation_profile="cpk.semantic-invocations.v1",
            ordinary_verification_invocations=True, http_sample_support=self.support.http_samples,
            managed_verification_support=self.support)
        from control_plane_kit_core.types import RuntimeKind
        options = http_sample_service_options({RuntimeKind.DOCKER: registration})
        self.assertIs(options["managed_verification_support"], self.support)
        self.assertIs(options["managed_verification_registration"], registration)
        self.assertIs(options["http_sample_registration"], registration)
        self.assertIs(native.postgres_readiness_executor.managed_verification_support, self.support)
        self.assertIs(native.http_sample_executor.http_sample_support, self.support.http_samples)

    def test_structural_prepared_value_and_crossed_registered_gateway_refuse(self):
        with self.assertRaises(HttpSampleCompositionUnavailable):
            postgres_readiness_check_input(SimpleNamespace(binding=self.prepared.binding), self.support)
        binding = self.support.http_samples.gateway_binding
        reference = self.prepared.binding.observer.product
        support = replace(self.support, http_samples=replace(self.support.http_samples,
            gateway_binding=replace(binding, product=reference)))
        with self.assertRaises(HttpSampleCompositionUnavailable):
            postgres_readiness_route_input(self.prepared.route, support)
