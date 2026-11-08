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


class ManagedCompositionTests(unittest.TestCase):
    def setUp(self):
        # Reuse the owner's exact supplied-record fixture, not a copied state
        # machine. It explicitly establishes no current admission or dispatch.
        from tests.test_managed_verification_execution import ManagedVerificationRouteTests
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

    def test_complete_eight_node_plan_selects_both_native_executors_and_all_three_connectors(self):
        import os
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import control_plane_kit_core as core
        from control_plane_kit_core.postgres_readiness import PostgresReadinessObserver
        from control_plane_kit_core.products import OciImageReference, ProductReference
        from control_plane_kit_core.secret_selections import SecretVersionSelection, secret_selections_from_descriptor
        from control_plane_kit_core.topology import DeploymentGraph, validate_graph
        from control_plane_kit_core.topology.secret_selection import carry_forward_secret_selections
        from control_plane_kit_operations.http_sample_execution import HttpSampleExecutionSupport
        from control_plane_kit_operations.managed_verification_execution import ManagedVerificationExecutionSupport
        from control_plane_kit_interpreters.docker.connector_connection import DockerConnectorConnectionQualifier, ConnectorConnectionQualification
        from control_plane_kit_interpreters.docker.sdk import ConnectorConnectionProfile
        from control_plane_kit_servers_cpk_server.health_receiver_adapters import health_receiver_decoders
        from control_plane_kit_servers_cpk_server.http_sample_composition import gateway_http_sample_binding
        from control_plane_kit_servers_cpk_server.installation import installation_secret_version_choices
        from control_plane_kit_servers_cpk_server.managed_verification_composition import native_verification_executors
        from http_sample_installation_assembly import assemble

        previous = Path.cwd()
        with TemporaryDirectory(prefix="cpk2089-static-native-") as directory:
            try:
                os.chdir(directory)
                custody = Path(directory) / "commissioning"
                custody.mkdir(mode=0o700)
                # Coordinate only: this pure phase never inspects an image or
                # claims its qualification, credentials or operational health.
                image = OciImageReference("localhost", "control-plane-kit-servers/postgres-server",
                    "sha256:8ddc847725e9b1d4c931dce2590c59d5bf68104c5804441ed2ed80e99778b48b")
                fixture, original, _, graph, gateway, _ = assemble(commissioning_directory=custody, postgres_image=image)
                uses = sorted({(value.reference, value.intent) for node in graph.nodes.values()
                    for value in node.secret_selections}, key=lambda pair:(pair[0].reference_id, pair[1].value))
                versions = tuple(SecretVersionSelection(reference, intent, "pure-static-version-" + str(index))
                    for index, (reference, intent) in enumerate(uses))
                choices = installation_secret_version_choices(original, versions)
                desired = carry_forward_secret_selections(DeploymentGraph(graph.name), graph,
                    {node:secret_selections_from_descriptor(values) for node, values in choices.items()})
                pair = validate_graph(DeploymentGraph(graph.name)), validate_graph(desired)
                for value in pair:
                    value.require_valid()
                plan = core.compile_managed_verification_bootstrap_activity_plan(*pair)
                self.assertTrue(plan.ready_for_execution)
                pg = original.postgres_product.product
                check, = desired.node(original.postgres_node_id).block_spec.verification.checks
                delivery, = pg.runtime_contract.secret_deliveries
                observer = PostgresReadinessObserver(ProductReference.from_document(original.postgres_product),
                    image, check.provider_socket, check.authentication.database, check.authentication.username,
                    delivery.target_path, delivery.path_binding.environment_name)
                support = ManagedVerificationExecutionSupport(HttpSampleExecutionSupport(gateway_http_sample_binding(gateway), "control"),
                    (observer,), health_receiver_decoders(gateway_documents=(gateway,)))
                resolver = SimpleNamespace(resolve=lambda *_:self.fail("pure qualification resolved secret"))
                native = compose_managed_verification_runtime(DockerRuntimeInterpreter(client=SimpleNamespace()),
                    support=support, resolver=resolver, public_resolver=None, clock_epoch_ms=lambda:0)
                registration = RuntimeAdapterRegistration(native, invocation_profile="cpk.semantic-invocations.v1",
                    ordinary_verification_invocations=True, http_sample_support=support.http_samples,
                    managed_verification_support=support)
                executors = native_verification_executors(registration, plan, pair)
                self.assertEqual(set(executors), {"http_sample_executor", "postgres_readiness_executor"})
                connector = original.management.connector_product
                qualifier = DockerConnectorConnectionQualifier(ProductReference.from_document(connector),
                    connector.product.image.execution_reference, ConnectorConnectionProfile.MANAGED_WRAPPER_V1, **executors)
                activities = [item for item in plan.activities if type(item.operation) is core.ObserveManagementBootstrap
                    and item.operation.stage is core.ManagementBootstrapStage.CONNECTOR_CONNECTED]
                self.assertEqual(len(activities), 3)
                for item in activities:
                    runtime = desired.runtimes[item.operation.target.runtime_id]
                    self.assertIs(qualifier.qualify_shape(activity_id=item.activity_id, plan=plan,
                        current=pair[0], desired=pair[1], product_document=connector,
                        authority_ref=runtime.authority_ref), ConnectorConnectionQualification.FRESH)
            finally:
                os.chdir(previous)

    def test_legacy_http_plan_survives_shared_mixed_registration_in_real_bridge_and_connector(self):
        from http_sample_linked_qualification import LinkedHttpSampleQualificationTests
        from control_plane_kit_operations.managed_verification_execution import ManagedVerificationExecutionSupport
        from control_plane_kit_servers_cpk_server.health_receiver_adapters import health_receiver_decoders
        from unittest.mock import Mock
        case = LinkedHttpSampleQualificationTests()
        case.setUp()
        gateway = case.value.authored.documents["gateway"]
        support = ManagedVerificationExecutionSupport(case.support, (self.prepared.binding.observer,),
            health_receiver_decoders(gateway_documents=(gateway,)))
        adapter = compose_managed_verification_runtime(case.registration.adapter.adapter, support=support,
            resolver=Mock(), public_resolver=Mock(), clock_epoch_ms=lambda:150000)
        registration = RuntimeAdapterRegistration(adapter, invocation_profile="cpk.semantic-invocations.v1",
            ordinary_verification_invocations=True, http_sample_support=case.support,
            managed_verification_support=support)
        case.registration = registration
        case.native = replace(case.native, http_sample_registration=registration)
        case.bridge = replace(case.bridge, native=case.native, http_sample_registration=registration)
        inputs = dict(plan=case.plan, current=case.value.current, desired=case.desired,
            registered_products=case.products, runtime_authorities=(case.value.authority,))
        for name, select in (("bridge", case.select), ("connector", lambda:case.native.qualify(**inputs))):
            with self.subTest(owner=name):
                self.assertIsNotNone(select(), "upgraded registration lost an exact ready original HTTP-only plan")
        case.test_unselected_or_legacy_interpretation_retains_refusal()
        self.assertEqual(case.client.mock_calls, [])
