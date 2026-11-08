"""Actual legacy/new Operations constructor and selected Servers decoder join.

These explicitly selected source-cohort tests do not prepare plans, touch stores,
admit invocations or establish a SQL read. Default pinned tests remain separate.
"""
from dataclasses import fields, replace
import importlib
from pathlib import Path
import unittest

import control_plane_kit_core as core
from control_plane_kit_core.planning import PlanGraphSide
from control_plane_kit_core.products import ProductReference
from control_plane_kit_operations.health_receiver_trust import GatewayHealthReceiverTrust, HealthReceiverSelection
from health_receiver_join_fixtures import gateway_self_world
from test_health_receiver_adapters import HealthReceiverAdapterTests


class GatewayTargetContext(unittest.TestCase):
    def setUp(self):
        self.addCleanup(HealthReceiverAdapterTests.clear_product_modules)
        for module, root in (("control_plane_kit_core", "/reviewed-http-sample/core/src"),
                             ("control_plane_kit_operations", "/reviewed-http-sample/operations/src")):
            self.assertTrue(Path(importlib.import_module(module).__file__).resolve().is_relative_to(root))
        self.value = gateway_self_world()
        self.api = importlib.import_module("control_plane_kit_servers_cpk_server.health_receiver_adapters")
        self.reference = ProductReference.from_document(self.value.document)
        self.decoder = self.api.health_receiver_decoders(gateway_documents=(self.value.document,)).binding_for(
            self.reference, core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT)

    def selection(self, family, artifact=None):
        return HealthReceiverSelection("workspace-a", "revision-a", "projection-desired",
            PlanGraphSide.DESIRED_GRAPH, "gateway-a", "runtime-a", "control", self.reference,
            self.value.document, self.value.artifacts[family] if artifact is None else artifact)

    def decoded(self, artifact=None):
        return self.decoder.decoder.decode(self.selection("transit", artifact))


class LegacyGatewayTargetTests(GatewayTargetContext):
    def test_actual_earlier_constructor_and_existing_selected_trust_remain_valid(self):
        self.assertNotIn("gateway_target", {field.name for field in fields(GatewayHealthReceiverTrust)})
        trusted = self.decoded()
        configured = self.value.trust
        self.assertEqual((trusted.workspace_id, trusted.gateway_node_id, trusted.runtime_id),
            (configured.gateway_target.workspace_id, configured.gateway_target.node_id,
                configured.gateway_target.runtime_id))
        self.assertEqual((trusted.issuer, trusted.public_keys), (configured.issuer, configured.public_keys))


class FullGatewayTargetTests(GatewayTargetContext):
    def test_new_constructor_preserves_actual_selected_full_receiver_identity(self):
        self.assertIn("gateway_target", {field.name for field in fields(GatewayHealthReceiverTrust)})
        self.assertEqual(self.decoded().gateway_target, self.value.trust.gateway_target)

    def test_actual_owner_route_join_accepts_match_and_refuses_same_node_other_receiver(self):
        from control_plane_kit_operations.managed_verification_execution import (
            PreparedPostgresReadinessRoute, ManagedVerificationSupportUnavailable,
        )
        ingress = core.NamedPublicIngress("management", core.IngressAuthorityReference("fixture-zone"),
            core.PublicIngressTarget("gateway-a", "control"), "connector-a", "gateway.example.invalid")
        trusted = self.decoded()
        route = PreparedPostgresReadinessRoute("plan-a", self.selection("targets"),
            self.selection("transit"), self.decoder, trusted, self.value.config.target,
            self.value.config, self.value.binding, ingress, "control")
        self.assertEqual(route.gateway_target, trusted.gateway_target)
        foreign = replace(self.value.trust, gateway_target=replace(
            self.value.trust.gateway_target, receiver_id="f" * 32))
        artifact = self.value.transit.gateway_health_transit_configuration_artifact(foreign)
        decoded = self.decoded(artifact)
        self.assertEqual(decoded.gateway_target, foreign.gateway_target)
        self.assertEqual(decoded.gateway_node_id, trusted.gateway_node_id)
        with self.assertRaises(ManagedVerificationSupportUnavailable):
            replace(route, transit_selection=self.selection("transit", artifact), gateway_trust=decoded)
