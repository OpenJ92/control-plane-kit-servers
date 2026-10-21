"""Scoped borrowed capability laws; typed fixtures are not admitted history."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import control_plane_kit_core as core
from control_plane_kit_interpreters.docker.sdk import DockerSdkClient, DockerSdkResourceInspection, DockerSdkNetworkAttachment
from control_plane_kit_interpreters.docker.connector_connection import (
    ConnectorConnectionObservation, ConnectorConnectionOutcome, DockerConnectorConnectionObserver,
)
from control_plane_kit_operations.runtime_authorities import RegisteredRuntimeAuthorityStatus
from managed_native_material import NativeMaterial


class ManagedProviderClientTests(unittest.TestCase):
    def api(self):
        # Report an intentionally missing interface as a test assertion, not an
        # import/collection failure. No source scaffolding manufactures target red.
        from control_plane_kit_servers_cpk_server import managed_health_placement as placement
        for name in ("DockerRuntimeClientBinding", "DockerRuntimeClientSelector"):
            self.assertTrue(callable(getattr(placement, name, None)),
                "scoped provider capability is missing: " + name)
        return placement

    def world(self, *, retained=False):
        api = self.api()
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBootstrap
        from control_plane_kit_servers_cpk_server.managed_native_connection import DockerManagedNativeConnection
        world = NativeMaterial(retained=retained)
        sdk_api = Mock()
        sdk_api.timeout = 60
        underlying = SimpleNamespace(api=sdk_api, close=Mock())
        client = DockerSdkClient(client=underlying, connect_on_init=False)
        binding = api.DockerRuntimeClientBinding("workspace-a", "docker", world.authority.authority_ref, client)
        selector = api.DockerRuntimeClientSelector((binding,))
        clock = Mock(return_value=datetime(2026, 10, 20, tzinfo=timezone.utc))
        native = DockerManagedNativeConnection(selector, world.document, clock)
        bridge = ManagedHealthBootstrap((world.authored.documents["gateway"],), selector,
            endpoints=None, native=native).build(Mock())
        return SimpleNamespace(api=api, world=world, sdk_api=sdk_api, underlying=underlying,
            client=client, binding=binding, selector=selector, native=native, bridge=bridge, clock=clock)

    def selected(self, value, **changes):
        values = dict(workspace_id="workspace-a", runtime_id="docker", authority=value.world.authority)
        values.update(changes)
        return value.selector.select(**values)

    def test_scope_selection_is_exact_and_zero_io(self):
        value = self.world()
        self.assertIs(self.selected(value), value.binding)
        for changes in (dict(workspace_id="foreign"), dict(runtime_id="foreign"),
                dict(authority=replace(value.world.authority, status=RegisteredRuntimeAuthorityStatus.REVOKED)),
                dict(authority=replace(value.world.authority, workspace_id="foreign")),
                dict(authority=replace(value.world.authority, authority_ref=core.RuntimeAuthorityReference("foreign")))):
            with self.subTest(changes=tuple(changes)):
                self.assertIsNone(self.selected(value, **changes))
        self.assertEqual(value.sdk_api.mock_calls, [])
        value.clock.assert_not_called()
        value.underlying.close.assert_not_called()

    def test_duplicate_scope_and_non_sdk_client_are_invalid(self):
        value = self.world()
        with self.assertRaises(ValueError):
            value.api.DockerRuntimeClientSelector((value.binding, replace(value.binding)))
        with self.assertRaises(ValueError):
            value.api.DockerRuntimeClientBinding("workspace-a", "docker",
                value.world.authority.authority_ref, Mock())
        with self.assertRaises(ValueError):
            value.api.DockerRuntimeClientSelector(tuple(replace(value.binding, runtime_id="runtime-" + str(i))
                for i in range(65)))
        self.assertEqual(value.sdk_api.mock_calls, [])

    def test_fresh_whole_plan_selects_without_controller_placement(self):
        value = self.world()
        self.assertFalse(any(type(a.operation) is core.ObserveManagementBootstrap
            and a.operation.stage is core.ManagementBootstrapStage.GATEWAY_LOCAL_READY
            for a in value.world.plan.activities))
        expected = tuple(a.activity_id for a in value.world.plan.activities
            if type(a.operation) in (core.ObserveManagementBootstrap, core.ObserveNodeHealth))
        self.assertEqual(value.bridge.select(**value.world.selection()), expected)
        self.assertEqual(value.sdk_api.mock_calls, [])
        value.clock.assert_not_called()
        value.underlying.close.assert_not_called()

    def test_native_dispatch_uses_the_selected_borrowed_client_without_placement(self):
        value = self.world()
        observed = ConnectorConnectionObservation(ConnectorConnectionOutcome.UNKNOWN,
            value.world.request.effect_id, value.world.request.activity_id.value)
        calls = []
        def read(observer, request, **kwargs):
            calls.append((observer, request, kwargs))
            return observed
        with patch.object(DockerConnectorConnectionObserver, "observe", read):
            result = asyncio.run(value.bridge.observe_connection(value.world.realization,
                value.world.request, value.world.authority))
        self.assertEqual(len(calls), 1)
        observer, request, inputs = calls[0]
        self.assertIs(observer.client, value.binding.client)
        self.assertIs(request, value.world.request)
        self.assertIs(inputs["plan"], value.world.plan)
        self.assertEqual(result.effect_id, value.world.request.effect_id)
        value.underlying.close.assert_not_called()

    def test_retained_local_plan_refuses_wholly_before_native_read(self):
        value = self.world(retained=True)
        self.assertTrue(any(type(a.operation) is core.ObserveManagementBootstrap
            and a.operation.stage is core.ManagementBootstrapStage.GATEWAY_LOCAL_READY
            for a in value.world.plan.activities))
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthUnavailable
        with patch.object(DockerConnectorConnectionObserver, "observe") as read:
            self.assertIsNone(value.bridge.select(**value.world.selection()))
            with self.assertRaises(ManagedHealthUnavailable):
                asyncio.run(value.bridge.observe_connection(value.world.realization,
                    value.world.request, value.world.authority))
        read.assert_not_called()
        self.assertEqual(value.sdk_api.mock_calls, [])
        value.underlying.close.assert_not_called()

    def test_mixed_retained_infrastructure_new_workload_refuses_public_dispatch(self):
        self.api()
        from test_managed_health_bridge import ManagedHealthBridgeSelectionTests
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthUnavailable
        fixture = ManagedHealthBridgeSelectionTests()
        fixture.setUp()  # Actual compiled retained gateway/connector + new workload.
        realization, request, authority, _ = fixture.dispatch_inputs(local=False)
        reader = SimpleNamespace(observe=AsyncMock())
        bridge = replace(fixture.bridge, endpoints=None, reader=reader)
        with self.assertRaises(ManagedHealthUnavailable):
            asyncio.run(bridge.observe_signed(realization, request, authority))
        reader.observe.assert_not_awaited()
        fixture.bindings.assert_not_called()
        fixture.native.select.assert_not_called()

    def test_public_stages_dispatch_without_any_local_capability(self):
        self.api()
        from test_managed_health_bridge import ManagedHealthBridgeSelectionTests
        from control_plane_kit_interpreters.probes.health_transport import GatewayHealthTransportCode
        fixture = ManagedHealthBridgeSelectionTests()
        fixture.setUp()
        fixture.use_fresh_plan()
        for stage in (core.ManagementBootstrapStage.AUTHENTICATED_MANAGEMENT_PATH,
                core.ManagementBootstrapStage.GATEWAY_INGRESS_READY, None):
            with self.subTest(stage=stage):
                realization, request, authority, result = fixture.dispatch_inputs(local=False, stage=stage)
                reader = SimpleNamespace(observe=AsyncMock(return_value=SimpleNamespace(
                    code=GatewayHealthTransportCode.RECEIVED, result=result)))
                bridge = replace(fixture.bridge, endpoints=None, reader=reader)
                self.assertIs(asyncio.run(bridge.observe_signed(realization, request, authority)), result)
                args = reader.observe.call_args
                self.assertIs(args.args[0], request)
                self.assertIs(args.kwargs["plan"], realization.plan)
                self.assertIsNone(args.kwargs["local_destination"])
                self.assertEqual(args.kwargs["destination"].gateway_node_id.value, "gateway")
        fixture.bindings.assert_not_called()

    def test_native_cannot_supply_an_independent_selector(self):
        value = self.world()
        other = value.api.DockerRuntimeClientSelector((value.binding,))
        with self.assertRaises(ValueError):
            replace(value.bridge, native=replace(value.native, provider_clients=other))
        self.assertEqual(value.sdk_api.mock_calls, [])

    def test_local_reader_uses_only_the_exact_selected_binding(self):
        value = self.world(retained=True)
        api = value.api
        placement = api.DockerControllerPlacement(value.binding, "c" * 64)
        gateway = api.DockerGatewayBinding("workspace-a", "docker", value.world.authority.authority_ref,
            "gateway", "a" * 64, "b" * 64)
        bindings = Mock(return_value=gateway)
        reader = api.DockerGatewayEndpointReader((placement,), bindings)
        inputs = dict(provider_binding=value.binding, workspace_id="workspace-a", runtime_id="docker",
            authority=value.world.authority)
        self.assertIs(reader.select(**inputs), placement)
        self.assertIsNone(reader.select(**dict(inputs, provider_binding=replace(value.binding))))
        bindings.assert_not_called()
        network = DockerSdkResourceInspection("network", False, None, {}, network_id="a" * 64)
        def inspect(client, identity):
            self.assertIs(client, value.binding.client)
            return DockerSdkResourceInspection("node", True, None, {}, container_id=identity,
                network_attachments=(DockerSdkNetworkAttachment("a" * 64, "172.20.0.7"),))
        with (patch.object(DockerSdkClient, "inspect_network", autospec=True, return_value=network) as network_read,
                patch.object(DockerSdkClient, "inspect_container", inspect)):
            endpoint = reader.read(**inputs, gateway_node_id="gateway", socket_name="control", port=8000,
                graph_id="graph-original")
        network_read.assert_called_once_with(value.binding.client, "a" * 64)
        self.assertEqual(endpoint.endpoint.address.value, "http://172.20.0.7:8000")
        with self.assertRaises(api.GatewayPlacementUnavailable):
            reader.read(**dict(inputs, provider_binding=replace(value.binding)), gateway_node_id="gateway",
                socket_name="control", port=8000, graph_id="graph-original")
        self.assertEqual(bindings.call_count, 1)
        value.underlying.close.assert_not_called()
