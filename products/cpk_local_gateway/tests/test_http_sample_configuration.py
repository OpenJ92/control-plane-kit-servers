"""Sample process trust/slots; no grandparent admission or history claim."""
from dataclasses import replace
import importlib
import json
import os
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_core.products import ProductRuntimeContractCodec
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from gateway_control_fixtures import fixture


class HttpSampleConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.control_api = importlib.import_module("control_plane_kit_servers_cpk_local_gateway.control_configuration")
        self.value = fixture(self.control_api)
        self.api = importlib.import_module("control_plane_kit_servers_cpk_local_gateway.http_sample_configuration")
        from control_plane_kit_servers_cpk_local_gateway.http_sample_relay import GatewayHttpSampleTrust
        self.trust = GatewayHttpSampleTrust(self.value.config.target, "sample-controller",
                                            (self.value.world.transit.key_a,))
        self.artifact = self.api.gateway_http_sample_trust_artifact(self.trust)

    def test_closed_public_artifact_and_declared_source_contract_agree(self):
        self.assertEqual(self.api.gateway_http_sample_trust_from_artifact(self.artifact), self.trust)
        declared = self.api.gateway_http_sample_declared_runtime_contract()
        source = self.api.gateway_http_sample_source_runtime_contract(*self.value.artifacts, self.artifact)
        self.assertEqual(ProductRuntimeContractCodec().decode(source.descriptor()), source)
        self.assertEqual({(slot.artifact_id, slot.target_path) for slot in declared.configuration_requirements},
                         {(slot.artifact_id, slot.target_path) for slot in source.configuration_artifacts})
        self.assertIn(PublicStaticEnvironmentBinding(self.api.CONFIGURATION_ENVIRONMENT,
                                                        self.api.CONFIGURATION_PATH), source.public_environment)
        self.assertEqual(source.gateway_transit, declared.gateway_transit)

    def test_wrong_slot_purpose_duplicate_key_or_full_gateway_target_refuses(self):
        for artifact in (replace(self.artifact, target_path="/etc/other.json"),
                         replace(self.artifact, artifact_id="other")):
            with self.assertRaises(self.api.GatewayHttpSampleConfigurationError):
                self.api.gateway_http_sample_trust_from_artifact(artifact)
        raw = json.loads(self.artifact.content)
        for changes in ({"purpose": core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT.value},
                        {"public_keys": raw["public_keys"] * 2}, {"unexpected": "private-marker"}):
            with self.assertRaises(self.api.GatewayHttpSampleConfigurationError) as caught:
                self.api.decode_gateway_http_sample_trust(json.dumps(raw | changes).encode())
            self.assertEqual(str(caught.exception), "gateway HTTP sample configuration is invalid")
        other = replace(self.trust, gateway_target=replace(self.trust.gateway_target, receiver_id="c" * 32))
        with self.assertRaises(self.api.GatewayHttpSampleConfigurationError):
            self.api.gateway_http_sample_source_runtime_contract(
                *self.value.artifacts, self.api.gateway_http_sample_trust_artifact(other))

    def test_product_trust_uses_core_issuer_reference_and_key_identifier_domains(self):
        raw = json.loads(self.artifact.content)
        bad_key = raw["public_keys"][0] | {"key_id": "key with space"}
        for changes in ({"issuer": "sample controller"}, {"public_keys": [bad_key]}):
            with self.assertRaises(self.api.GatewayHttpSampleConfigurationError):
                self.api.decode_gateway_http_sample_trust(json.dumps(raw | changes).encode())
        long = replace(self.trust, issuer="a" * 129)
        artifact = self.api.gateway_http_sample_trust_artifact(long)
        self.assertEqual(self.api.gateway_http_sample_trust_from_artifact(artifact), long)
        self.assertEqual(self.api.gateway_http_sample_source_runtime_contract(
            *self.value.artifacts, artifact).configuration_artifacts[-1], artifact)

    def test_process_explicit_selection_loads_same_routes_and_trust_without_provider_io(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(self.api, "_read") as read:
            self.assertIsNone(self.api.load_http_sample_relay(self.value.relay, self.value.config))
            read.assert_not_called()
        with patch.dict(os.environ, {self.api.CONFIGURATION_ENVIRONMENT: self.api.CONFIGURATION_PATH}, clear=True), \
                patch.object(self.api, "_read", return_value=self.artifact.content.encode()) as read:
            selected = self.api.load_http_sample_relay(self.value.relay, self.value.config)
            self.assertEqual(selected.configuration, self.value.relay.configuration)
            self.assertEqual(selected.trust, self.trust)
            read.assert_called_once_with(self.api.CONFIGURATION_PATH, self.api.MAX_CONFIGURATION_BYTES)
        with patch.dict(os.environ, {self.api.CONFIGURATION_ENVIRONMENT: "/tmp/private-marker"}, clear=True), \
                patch.object(self.api, "_read") as read:
            with self.assertRaises(self.api.GatewayHttpSampleConfigurationError):
                self.api.load_http_sample_relay(self.value.relay, self.value.config)
            read.assert_not_called()

    def test_real_main_composes_sample_route_from_selected_public_material(self):
        from control_plane_kit_servers_cpk_local_gateway import server
        with patch.object(server, "GatewayConfiguration") as config, \
                patch("control_plane_kit_servers_cpk_local_gateway.health_relay_startup.load_health_relay",
                      return_value=self.value.relay), \
                patch.object(self.control_api, "read_gateway_control_configuration", return_value=self.value.config) as read_control, \
                patch.dict(os.environ, {self.api.CONFIGURATION_ENVIRONMENT: self.api.CONFIGURATION_PATH}, clear=True), \
                patch.object(self.api, "_read", return_value=self.artifact.content.encode()), \
                patch.object(server.uvicorn, "run") as run:
            config.from_environment.return_value.port = 8000
            self.assertEqual(server.main(), 0)
            read_control.assert_called_once_with()
        app = run.call_args.args[0]
        self.assertIn("/cpk/verification/http", {route.path for route in app.routes})
        self.assertIn("/cpk/health/{health_kind}", {route.path for route in app.routes})

    def covered_receiver(self, *, full=True):
        from test_http_sample_relay import Fixture
        from control_plane_kit_core.verification import VerificationContract
        from control_plane_kit_core.http_verification_sample_installation import HttpVerificationSampleCheckBinding
        from control_plane_kit_core.http_verification_samples import http_verification_check_digest
        value = Fixture(8081)
        ready = value.check
        live = replace(ready, check_id="live", path="/health/live")
        declared = (ready, live)
        configured = replace(value.binding.configuration, checks=tuple(
            HttpVerificationSampleCheckBinding(check.check_id, http_verification_check_digest(check))
            for check in declared if full or check is ready))
        return replace(value.binding, configuration=configured, verification_contract=VerificationContract(declared))

    def test_acquired_checks_preserve_declaration_order_with_exact_installed_coverage(self):
        from control_plane_kit_servers_cpk_server.http_sample_composition import http_sample_original_checks
        receiver = self.covered_receiver()
        self.assertEqual(tuple(entry.check.check_id for entry in receiver.checks), ("live", "ready"))
        self.assertEqual(tuple(check.check_id for check in http_sample_original_checks(receiver)), ("ready", "live"))

    def test_missing_installed_original_check_refuses_acquisition_projection(self):
        from control_plane_kit_servers_cpk_server.http_sample_composition import (
            http_sample_original_checks, HttpSampleCompositionUnavailable,
        )
        with self.assertRaises(HttpSampleCompositionUnavailable):
            http_sample_original_checks(self.covered_receiver(full=False))
