"""Source composition evidence, not managed-image or admitted-run qualification."""
import asyncio
from dataclasses import asdict, replace
from datetime import datetime, timezone
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import control_plane_kit_core as core
from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from control_plane_kit_core.planning import WaitForHealthy
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, validate_graph
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_interpreters.docker.connector_connection import (
    ConnectorConnectionObservation, ConnectorConnectionOutcome, DockerConnectorConnectionObserver,
)
from control_plane_kit_interpreters.docker.sdk import ConnectorConnectionProfile, DockerSdkClient
from control_plane_kit_operations.effect_outcome_evidence import (
    NativeConnectionObservation, NativeConnectionOutcome, NativeConnectionRefused,
)
from managed_native_material import NativeMaterial


class ManagedNativeConnectionTests(unittest.TestCase):
    def setUp(self):
        from control_plane_kit_servers_cpk_server.managed_health_placement import (
            DockerControllerPlacement, DockerGatewayEndpointReader, DockerRuntimeClientBinding, DockerRuntimeClientSelector,
        )
        from control_plane_kit_servers_cpk_server.managed_native_connection import DockerManagedNativeConnection
        self.world = NativeMaterial()
        self.api = Mock()
        self.api.timeout = 60
        self.api.inspect_container.side_effect = RuntimeError("private provider failure")
        self.client = DockerSdkClient(client=SimpleNamespace(api=self.api), connect_on_init=False)
        self.clock = Mock(return_value=datetime(2026, 10, 20, tzinfo=timezone.utc))
        self.binding = Mock(side_effect=AssertionError("native reads must not resolve gateway bindings"))
        self.provider = DockerRuntimeClientBinding("workspace-a", "docker", self.world.authority.authority_ref, self.client)
        self.provider_clients = DockerRuntimeClientSelector((self.provider,))
        self.placement = DockerControllerPlacement(self.provider, "c" * 64)
        self.endpoints = DockerGatewayEndpointReader((self.placement,), self.binding)
        self.native = DockerManagedNativeConnection(self.provider_clients, self.world.document, self.clock)

    def select(self, world=None, native=None, **changes):
        inputs = (world or self.world).selection()
        inputs.update(changes)
        return (native or self.native).select(**inputs)

    def bridge(self, native=None, world=None):
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBootstrap
        world = world or self.world
        return ManagedHealthBootstrap((world.authored.documents["gateway"],),
            self.provider_clients, endpoints=self.endpoints, native=native or self.native).build(Mock())

    def observe(self, *, world=None, request=None, authority=None, bridge=None):
        world = world or self.world
        return asyncio.run((bridge or self.bridge()).observe_connection(world.realization,
            request or world.request, authority or world.authority))

    def result(self, outcome=ConnectorConnectionOutcome.CONNECTED, *, sample=True):
        values = dict(effect_id=self.world.request.effect_id, activity_id=self.world.request.activity_id.value)
        if sample:
            values.update(container_id="c" * 64, sample_start="2026-10-20T00:00:00.000000001Z",
                sample_end="2026-10-20T00:00:01.123456789Z")
        if outcome in (ConnectorConnectionOutcome.CONNECTED, ConnectorConnectionOutcome.DISCONNECTED):
            values.update(ready_connections=4 if outcome is ConnectorConnectionOutcome.CONNECTED else 0,
                connector_id="ae232234-79c8-48fe-9b67-123456789abc")
        return ConnectorConnectionObservation(outcome, **values)

    def assert_pure(self):
        self.assertEqual(self.api.mock_calls, [])
        self.clock.assert_not_called()
        self.binding.assert_not_called()

    def test_fresh_and_retained_complete_plan_selection_is_pure(self):
        for options in ({}, {"retained": True}, {"retained_image": True}):
            with self.subTest(options=options):
                world = self.world if not options else NativeMaterial(**options)
                native = replace(self.native, product_document=world.document)
                # Real accepted interpreter qualification, with genuine compiled graphs.
                self.assertEqual(self.select(world, native), (world.request.activity_id,))
        self.assert_pure()

    def test_current_authority_and_unique_actual_sdk_binding_are_required(self):
        for authorities in ((), (self.world.authority, self.world.authority),
                (replace(self.world.authority, workspace_id="workspace-b"),)):
            with self.subTest(authorities=authorities):
                self.assertIsNone(self.select(runtime_authorities=authorities))
        for bindings in ((), (replace(self.provider, runtime_id="other"),)):
            with self.subTest(bindings=len(bindings)):
                self.assertIsNone(self.select(native=replace(self.native,
                    provider_clients=replace(self.provider_clients, bindings=bindings))))
        with self.assertRaises(ValueError):
            replace(self.provider_clients, bindings=(self.provider, self.provider))
        with self.assertRaises(ValueError):
            replace(self.provider, client=Mock())
        self.assert_pure()

    def test_trusted_document_must_match_registration_and_graph(self):
        products = self.world.products
        connector = next(item for item in products if item.reference == self.world.reference)
        other_document = ProductDescriptorCodec().encode_document(replace(self.world.document.product,
            image=replace(self.world.document.product.image, digest="sha256:" + "b" * 64)))
        for values in ((), (*products, connector), tuple(item for item in products if item is not connector),
                tuple(replace(item, descriptor_document=other_document,
                    reference=ProductReference.from_document(other_document)) if item is connector else item
                    for item in products)):
            with self.subTest(count=len(values)):
                self.assertIsNone(self.select(registered_products=values))
        self.assertIsNone(self.select(native=replace(self.native, product_document=other_document)))
        changed = self.world.desired.update_node(replace(self.world.desired.nodes["connector"],
            metadata={"product_identity": self.world.reference.identity.key,
                "product_descriptor_digest": "f" * 64}))
        self.assertIsNone(self.select(desired=changed))
        self.assert_pure()

    def test_original_whole_plan_and_selected_profile_reach_interpreter(self):
        main_thread, calls = threading.get_ident(), []
        def observed(observer, request, **inputs):
            calls.append((observer, request, inputs, threading.get_ident()))
            return self.result()
        with patch.object(DockerConnectorConnectionObserver, "observe", observed):
            result = self.observe()
        observer, request, inputs, thread = calls[0]
        self.assertEqual(len(calls), 1)
        self.assertIs(observer.client, self.client)
        self.assertIs(observer.profile, ConnectorConnectionProfile.MANAGED_WRAPPER_V1)
        self.assertEqual(observer.product_reference, self.world.reference)
        self.assertEqual(observer.image_reference, self.world.document.product.image.execution_reference)
        self.assertIs(observer.clock, self.clock)
        self.assertIs(request, self.world.request)
        self.assertIs(inputs["plan"], self.world.plan)
        self.assertEqual(inputs["current"], validate_graph(self.world.current))
        self.assertEqual(inputs["desired"], validate_graph(self.world.desired))
        # Keep every original authored descriptor field across the effect boundary.
        for side, stored in (("current", self.world.realization.base_graph),
                ("desired", self.world.realization.desired_graph)):
            graph = inputs[side].require_valid()
            self.assertEqual(DEFAULT_GRAPH_CODEC.encode(graph), stored.graph_descriptor)
        self.assertIsNone(inputs.get("installation_request"))
        self.assertIsNone(inputs.get("installation_receipt"))
        self.assertNotEqual(main_thread, thread)
        self.assertIs(type(result), NativeConnectionObservation)
        self.assert_pure()

    def test_retained_original_installation_pair_is_passed_unchanged(self):
        for options in ({"retained": True}, {"retained_image": True}):
            with self.subTest(options=options):
                world = NativeMaterial(**options)
                native = replace(self.native, product_document=world.document)
                # Patched identity assertion only; these inputs are not an admitted workflow.
                calls = []
                def observed(observer, request, **inputs):
                    calls.append((request, inputs))
                    return ConnectorConnectionObservation(ConnectorConnectionOutcome.REFUSED)
                with patch.object(DockerConnectorConnectionObserver, "observe", observed):
                    self.assertIs(type(self.observe(world=world, bridge=self.bridge(native, world))), NativeConnectionRefused)
                self.assertEqual(len(calls), 1)
                request, inputs = calls[0]
                self.assertIs(request, world.request)
                self.assertIs(inputs["plan"], world.plan)
                self.assertEqual(inputs["current"], validate_graph(world.current))
                self.assertEqual(inputs["desired"], validate_graph(world.desired))
                self.assertIs(inputs["installation_request"], world.realization.connector_installation.original_request)
                self.assertIs(inputs["installation_receipt"], world.realization.connector_installation.receipt)
        self.assert_pure()

    def test_every_completed_result_preserves_correlation_and_nanoseconds(self):
        for outcome, sample in ((ConnectorConnectionOutcome.CONNECTED, True),
                (ConnectorConnectionOutcome.DISCONNECTED, True),
                (ConnectorConnectionOutcome.UNKNOWN, True), (ConnectorConnectionOutcome.UNKNOWN, False)):
            with self.subTest(outcome=outcome, sample=sample):
                original = self.result(outcome, sample=sample)
                with patch.object(DockerConnectorConnectionObserver, "observe", return_value=original) as observe:
                    result = self.observe()
                observe.assert_called_once()
                self.assertIs(type(result), NativeConnectionObservation)
                self.assertIs(result.outcome, NativeConnectionOutcome(outcome.value))
                for name in ("effect_id", "activity_id", "container_id", "sample_start", "sample_end",
                        "ready_connections", "connector_id"):
                    self.assertEqual(getattr(result, name), getattr(original, name))
        self.assert_pure()

    def test_refused_is_distinct_from_unknown_and_has_no_sample(self):
        with patch.object(DockerConnectorConnectionObserver, "observe",
                return_value=ConnectorConnectionObservation(ConnectorConnectionOutcome.REFUSED)) as observe:
            self.assertEqual(self.observe(), NativeConnectionRefused())
        observe.assert_called_once()
        self.assert_pure()

    def test_malformed_or_uncorrelated_result_is_fixed_read_failure(self):
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthUnavailable
        valid = self.result()
        for result in (None, SimpleNamespace(**asdict(valid)), replace(valid, effect_id="other"),
                replace(valid, activity_id="other"), replace(valid, outcome="connected"),
                replace(valid, ready_connections=True), replace(valid, sample_end=None),
                replace(valid, sample_start="private provider text"),
                replace(valid, outcome=ConnectorConnectionOutcome.REFUSED)):
            with self.subTest(result_type=type(result).__name__):
                with patch.object(DockerConnectorConnectionObserver, "observe", return_value=result):
                    with self.assertRaisesRegex(ManagedHealthUnavailable, "^managed health is unavailable$") as caught:
                        self.observe()
                self.assertIsNone(caught.exception.__context__)
        with patch.object(DockerConnectorConnectionObserver, "observe", side_effect=RuntimeError("private provider text")):
            with self.assertRaisesRegex(ManagedHealthUnavailable, "^managed health is unavailable$") as caught:
                self.observe()
            self.assertIsNone(caught.exception.__context__)

    def test_dispatch_rechecks_authority_workspace_and_exact_operation(self):
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthUnavailable
        for authority in (replace(self.world.authority, workspace_id="workspace-b"),
                replace(self.world.authority, registration_id="replacement-registration")):
            with self.subTest(authority=authority.registration_id):
                with self.assertRaises(ManagedHealthUnavailable):
                    self.observe(authority=authority)
        request = replace(self.world.request, source=replace(self.world.request.source, workspace_id="workspace-b"))
        with self.assertRaises(ManagedHealthUnavailable):
            self.observe(request=request)
        altered = replace(self.world.request, operation=replace(self.world.request.operation,
            stage=core.ManagementBootstrapStage.GATEWAY_LOCAL_READY))
        with self.assertRaises(ManagedHealthUnavailable):
            self.observe(request=altered)
        self.assert_pure()

    def test_real_observer_unknown_and_retained_refusal_never_fall_back(self):
        # Real accepted SDK/observer sees one failed passive read. No helper API exists.
        result = self.observe()
        self.assertEqual(result, NativeConnectionObservation(NativeConnectionOutcome.UNKNOWN,
            self.world.request.effect_id, self.world.request.activity_id.value))
        self.api.inspect_container.assert_called_once()
        self.assertEqual(len(self.api.mock_calls), 1)
        self.api.reset_mock()
        retained = NativeMaterial(retained=True)
        retained.realization.connector_installation = None
        native = replace(self.native, product_document=retained.document)
        self.assertEqual(self.observe(world=retained, bridge=self.bridge(native, retained)), NativeConnectionRefused())
        self.assertEqual(self.api.mock_calls, [])
        self.binding.assert_not_called()

    def test_retained_image_real_observer_reads_with_original_proof_and_returns_current_unknown(self):
        world = NativeMaterial(retained_image=True)
        native = replace(self.native, product_document=world.document)
        original = world.realization.connector_installation.original_request
        self.assertNotEqual(original.effect_id, world.request.effect_id)
        self.assertNotEqual(original.activity_id, world.request.activity_id)
        # Actual observer and DockerSdkClient; the existing unavailable provider
        # supplies no connected sample and performs no external operation.
        result = self.observe(world=world, bridge=self.bridge(native, world))
        self.assertEqual(result, NativeConnectionObservation(NativeConnectionOutcome.UNKNOWN,
            world.request.effect_id, world.request.activity_id.value))
        self.api.inspect_container.assert_called_once()
        self.assertEqual(len(self.api.mock_calls), 1)
        self.clock.assert_not_called()
        self.binding.assert_not_called()

    def test_retained_image_missing_or_foreign_original_proof_refuses_before_sdk(self):
        world = NativeMaterial(retained_image=True)
        native = replace(self.native, product_document=world.document)
        # Independently valid typed installation, but for different selected
        # receiver/configuration material. Do not forge an admitted history row.
        foreign = NativeMaterial(retained=True).realization.connector_installation
        self.assertNotEqual(foreign.original_request.products, world.request.products)
        for installation in (None, foreign):
            with self.subTest(missing=installation is None):
                world.realization.connector_installation = installation
                self.assertEqual(self.observe(world=world, bridge=self.bridge(native, world)), NativeConnectionRefused())
                self.assert_pure()

    def test_unsupported_whole_plan_cannot_reach_any_observation(self):
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthUnavailable
        # A real compiled legacy graph contains WaitForHealthy and no managed chain.
        graph = self.world.desired
        legacy = replace(graph, runtimes={"docker": replace(graph.runtimes["docker"], management=None)})
        plan = core.compile_graph_activity_plan(validate_graph(self.world.current), validate_graph(legacy))
        self.assertTrue(any(type(item.operation) is WaitForHealthy for item in plan.activities))
        self.assertIsNone(self.select(plan=plan, desired=legacy))
        self.world.realization.plan = plan
        self.world.realization.desired_graph.graph_descriptor = DEFAULT_GRAPH_CODEC.encode(legacy)
        with patch.object(DockerConnectorConnectionObserver, "observe") as observed:
            with self.assertRaises(ManagedHealthUnavailable):
                self.observe()
        observed.assert_not_called()
        self.assert_pure()

    def test_real_process_factory_injects_concrete_bridge_into_operations_owner(self):
        from control_plane_kit_servers_cpk_server import server, operations_application as composition
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBootstrap
        config = SimpleNamespace(runtime_dispatcher=SimpleNamespace(enabled=False),
            ingress_interpreters=SimpleNamespace(enabled=False), managed_health=ManagedHealthBootstrap(
                (self.world.authored.documents["gateway"],), self.provider_clients,
                endpoints=self.endpoints, native=self.native))
        provider = SimpleNamespace(metadata_reader=None, authorized_resolver=Mock(), delegation_key_generator=None)
        with patch.object(server, "_runtime_observer", return_value=Mock()):
            ports = server._operations_effect_ports(config, provider)
        self.assertIs(ports.managed_health.native, self.native)
        owner, actual = [], composition.ExecutionCoordinator
        def create(*args, **kwargs):
            value = actual(*args, **kwargs)
            owner.append(value)
            return value
        uow = Mock(side_effect=AssertionError("composition must not open a transaction"))
        ids = composition.OperationsIdFactories(*(Mock() for _ in range(5)))
        with patch.object(composition, "ExecutionCoordinator", side_effect=create):
            composition.OperationsApplicationFactory(uow, ports, ids)()
        bridge = owner[0]._managed_health
        self.assertIs(bridge, ports.managed_health)
        with patch.object(self.client, "run_http_probe", side_effect=AssertionError("legacy fallback")) as probe:
            result = self.observe(bridge=bridge)
        self.assertIs(result.outcome, NativeConnectionOutcome.UNKNOWN)
        probe.assert_not_called()
        uow.assert_not_called()
