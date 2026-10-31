"""#188 new-law targets: real product values and SDK boundary, not controller policy."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
from threading import Event, Thread
import time
import unittest
from unittest.mock import Mock, patch

import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.products import ProductRuntimeContractCodec, ProductDescriptorCodec
from control_plane_kit_core.secrets import (
    SecretFileDelivery, SecretFilePathBinding, SecretReference, SecretUseIntent,
)
from control_plane_kit_servers_cloudflared_connector import managed
from control_plane_kit_servers_cloudflared_connector.readiness import ConnectionSample
from managed_control_fixtures import fixture, token, request


class ManagedContractTests(unittest.TestCase):
    def test_declared_contract_requires_real_control_material_before_instantiation(self):
        # A missing entrance is an interface assertion, not semantic-red evidence.
        declaration_factory = getattr(managed, "control_declaration", None)
        contract_factory = getattr(managed, "declared_runtime_contract", None)
        self.assertTrue(callable(declaration_factory), "public control declaration is unavailable")
        self.assertTrue(callable(contract_factory), "required contract factory is unavailable")
        declaration = declaration_factory()
        contract = contract_factory()
        self.assertEqual(declaration, fixture().config.declaration)
        self.assertEqual(ProductRuntimeContractCodec().decode(contract.descriptor()), contract)
        self.assertEqual(contract.configuration_requirements, (
            core.ConfigurationArtifactRequirement(
                "cloudflared-control", "/etc/cpk/cloudflared/control.json",
                ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY),
        ))
        self.assertEqual(contract.configuration_artifacts, ())
        self.assertEqual(contract.secret_deliveries, ())
        self.assertEqual(contract.sockets.provider_names(), ("control",))
        self.assertEqual(contract.sockets.requirement_names(), ())
        self.assertEqual([(port.provider_socket, port.container_port)
                          for port in contract.provider_ports], [("control", 8000)])
        self.assertEqual(contract.control_surfaces, (declaration.surface,))
        self.assertEqual([(item.name, item.value) for item in contract.public_environment],
                         [("CPK_WRAPPER_CONFIGURATION_FILE", "/etc/cpk/cloudflared/control.json")])
        self.assertEqual({item.value for item in contract.capabilities},
                         {"health-checkable", "node-controllable"})
        self.assertEqual(contract.verification.checks, ())
        self.assertEqual(contract.retained_data_mounts, ())
        from control_plane_kit_core.products import ProductInstanceConfiguration, ProductInstantiationError
        with self.assertRaises(ProductInstantiationError):
            ProductInstanceConfiguration.from_contract(contract)

    def test_actual_source_contract_still_refuses_absent_token_material(self):
        artifact = managed.control_configuration_artifact(fixture().config)
        with self.assertRaises(managed.ConnectorConfigurationError):
            managed.source_runtime_contract(artifact, None)

    def test_real_contract_has_only_management_provider_and_scoped_token(self):
        value = fixture()
        artifact = managed.control_configuration_artifact(value.config)
        delivery = SecretFileDelivery('/run/secrets/tunnel', SecretReference('secret://generated/ingress/test'),
            SecretUseIntent.CLOUDFLARE_TUNNEL_TOKEN,
            path_binding=SecretFilePathBinding('TUNNEL_TOKEN_FILE'))
        contract = managed.source_runtime_contract(artifact, delivery)
        self.assertEqual(ProductRuntimeContractCodec().decode(contract.descriptor()), contract)
        self.assertEqual(contract.sockets.provider_names(), ('control',))
        self.assertEqual(contract.sockets.requirement_names(), ())
        self.assertEqual([(p.provider_socket, p.container_port) for p in contract.provider_ports], [('control', 8000)])
        self.assertEqual(contract.control_surfaces, (value.config.declaration.surface,))
        self.assertEqual(contract.secret_deliveries, (delivery,))
        self.assertEqual(contract.configuration_artifacts, (artifact,))
        self.assertEqual(artifact.file_mode.value, '0444')
        self.assertEqual(contract.retained_data_mounts, ())
        self.assertEqual(contract.verification.checks, ())
        self.assertEqual({c.value for c in contract.capabilities}, {'health-checkable', 'node-controllable'})
        self.assertEqual(core.ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode()), value.config)
        self.assertEqual([(e.name, e.value) for e in contract.public_environment],
            [('CPK_WRAPPER_CONFIGURATION_FILE', artifact.target_path)])
        old = ProductDescriptorCodec().decode_document(
            (Path(__file__).resolve().parents[1] / 'product.cpk.json').read_bytes()).product
        self.assertEqual(old.runtime_contract.sockets.provider_names(), ())
        self.assertEqual(old.image.digest, 'sha256:b5db8bec60f852c1cb488fe6ea79efa38d1016878acd05d2a83089c50b94909e')

    def test_foreign_surface_and_missing_readiness_are_refused(self):
        value = fixture().config
        for kinds in ((core.NodeHealthReadKind.LIVENESS,), (core.NodeHealthReadKind.READINESS,)):
            with self.subTest(kinds=kinds), self.assertRaises(managed.ConnectorConfigurationError):
                managed.control_configuration_artifact(replace(value, declaration=replace(value.declaration,
                    surface=replace(value.declaration.surface, health_reads=kinds))))
        foreign = core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, 'elsewhere')
        value = replace(value, target=replace(value.target, provider_socket_name=foreign),
            declaration=replace(value.declaration, surface=replace(value.declaration.surface, provider_socket_name=foreign)))
        with self.assertRaises(managed.ConnectorConfigurationError):
            managed.control_configuration_artifact(value)

    def test_wrong_token_purpose_or_environment_binding_is_refused(self):
        artifact = managed.control_configuration_artifact(fixture().config)
        correct = SecretFileDelivery('/run/secrets/tunnel', SecretReference('secret://generated/ingress/test'),
            SecretUseIntent.CLOUDFLARE_TUNNEL_TOKEN, path_binding=SecretFilePathBinding('TUNNEL_TOKEN_FILE'))
        for delivery in (None, replace(correct, intent=SecretUseIntent.POSTGRES_PASSWORD),
                         replace(correct, path_binding=None),
                         replace(correct, path_binding=SecretFilePathBinding('TUNNEL_TOKEN'))):
            with self.subTest(delivery=type(delivery)), self.assertRaises(managed.ConnectorConfigurationError):
                managed.source_runtime_contract(artifact, delivery)

    def test_contract_revalidates_foreign_or_malformed_artifact_content(self):
        value = fixture().config
        artifact = managed.control_configuration_artifact(value)
        delivery = SecretFileDelivery('/run/secrets/tunnel', SecretReference('secret://generated/ingress/test'),
            SecretUseIntent.CLOUDFLARE_TUNNEL_TOKEN, path_binding=SecretFilePathBinding('TUNNEL_TOKEN_FILE'))
        foreign = core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, 'elsewhere')
        foreign_value = replace(value, target=replace(value.target, provider_socket_name=foreign),
            declaration=replace(value.declaration, surface=replace(value.declaration.surface, provider_socket_name=foreign)))
        foreign_content = core.ReceiverNodeControlConfigurationCodec().encode_bytes(foreign_value).decode()
        for content in ('{}', foreign_content):
            with self.subTest(content_kind='malformed-schema' if content == '{}' else 'foreign'):
                candidate = replace(artifact, content=content)
                with self.assertRaises(managed.ConnectorConfigurationError):
                    managed.source_runtime_contract(candidate, delivery)


class ManagedHealthTests(unittest.TestCase):
    def test_native_connection_mapping_and_dead_process(self):
        for sample, expected in ((ConnectionSample('connected', ready_connections=1,
                connector_id='77a0325c-ff03-4be4-8064-d940252751c3'), 'healthy'),
                (ConnectionSample('disconnected', ready_connections=0,
                connector_id='77a0325c-ff03-4be4-8064-d940252751c3'), 'unhealthy'),
                (ConnectionSample('unknown', 'timeout'), 'unknown')):
            with self.subTest(expected=expected):
                alive = [True]
                probe = Mock(return_value=sample)
                health = managed.ConnectorHealth(native_alive=lambda: alive[0], read_connection=probe)
                self.assertEqual(health.liveness().value, 'healthy')
                probe.assert_not_called()
                self.assertEqual(health.readiness().value, expected)
                alive[0] = False
                probe.reset_mock()
                self.assertEqual(health.liveness().value, 'unhealthy')
                self.assertEqual(health.readiness().value, 'unhealthy')
                probe.assert_not_called()

    def test_stop_or_native_death_overrides_late_success_or_exception(self):
        for stopping in (False, True):
            for raises in (False, True):
                with self.subTest(stopping=stopping, raises=raises):
                    alive = [True]
                    def probe():
                        if stopping:
                            health.stop()
                        else:
                            alive[0] = False
                        if raises:
                            raise ValueError('secret late error')
                        return ConnectionSample('connected', ready_connections=1,
                            connector_id='77a0325c-ff03-4be4-8064-d940252751c3')
                    health = managed.ConnectorHealth(native_alive=lambda: alive[0], read_connection=probe)
                    self.assertEqual(health.readiness().value, 'unhealthy')

    def test_concurrent_probe_returns_unknown_without_second_native_read(self):
        entered, release = Event(), Event()
        calls = []
        results = []
        def probe():
            calls.append(1)
            entered.set()
            if not release.wait(2):
                raise AssertionError('fixture release deadline')
            return ConnectionSample('unknown', 'timeout')
        health = managed.ConnectorHealth(native_alive=lambda: True, read_connection=probe)
        thread = Thread(target=lambda: results.append(health.readiness()))
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertEqual(health.readiness().value, 'unknown')
            self.assertEqual(len(calls), 1)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual([r.value for r in results], ['unknown'])

    def test_unexpected_native_reader_error_is_unknown_without_candidate_detail(self):
        health = managed.ConnectorHealth(native_alive=lambda: True,
            read_connection=Mock(side_effect=ValueError('secret fixture must not escape')))
        self.assertEqual(health.readiness().value, 'unknown')


@contextmanager
def running(test, configuration, health):
    server = managed.create_control_server(configuration, health, address=('127.0.0.1', 0), clock=lambda: 150)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 2
        while not server.cpk_is_serving:
            if time.monotonic() > deadline:
                raise AssertionError('SDK did not observe serving')
            time.sleep(0.001)
        yield server
    finally:
        # shutdown() can block if serve_forever never entered. Always close.
        cleanup = Thread(target=server.shutdown, daemon=True)
        cleanup.start()
        try:
            cleanup.join(2)
        finally:
            server.server_close()
        thread.join(2)
        test.assertFalse(thread.is_alive())
        test.assertFalse(cleanup.is_alive())


class ManagedSdkBoundaryTests(unittest.TestCase):
    def test_sdk_denial_before_native_io_and_correlated_ready_result(self):
        value = fixture()
        probe = Mock(return_value=ConnectionSample('unknown', 'transport_unavailable'))
        health = managed.ConnectorHealth(native_alive=lambda: True, read_connection=probe)
        with running(self, value.config, health) as host:
            for credential in (None, token(value, static=True), token(value, request_changes={
                    'target': replace(value.config.target, receiver_id='f' * 32)})):
                self.assertEqual(request(host, '/__control/health/readiness', credential)[0], 401)
            probe.assert_not_called()
            status, body, _ = request(host, '/__control/health/readiness', token(value))
            self.assertEqual(status, 200)
            decoded = json.loads(body)
            self.assertEqual(decoded['outcome'], 'unknown')
            self.assertEqual(decoded['request_id'], 'health-request')
            self.assertEqual(probe.call_count, 1)
            health.stop()
            status, body, _ = request(host, '/__control/health/readiness', token(value))
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['outcome'], 'unhealthy')
            self.assertEqual(probe.call_count, 1)

    def test_invalid_configuration_is_refused_before_any_bind(self):
        with self.assertRaises(managed.ConnectorConfigurationError) as caught:
            managed.create_control_server(None, Mock(), address=('invalid host cannot bind', 0))
        self.assertNotIn('invalid host', str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

    def test_well_typed_foreign_surface_is_refused_before_bind(self):
        value = fixture().config
        foreign = core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, 'elsewhere')
        value = replace(value, target=replace(value.target, provider_socket_name=foreign),
            declaration=replace(value.declaration, surface=replace(value.declaration.surface, provider_socket_name=foreign)))
        with patch('control_plane_kit_server_sdk.stdlib.CpkThreadingHTTPServer.server_bind') as bind:
            with self.assertRaises(managed.ConnectorConfigurationError):
                managed.create_control_server(value, Mock(), address=('127.0.0.1', 0))
            bind.assert_not_called()
