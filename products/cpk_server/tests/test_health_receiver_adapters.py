"""Real selected receiver parsing/verifying joined to pinned Operations coverage."""
from dataclasses import replace
import importlib
import importlib.util
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_core.products import ProductReference
from control_plane_kit_core.configuration import ConfigurationMediaType, ConfigurationFileMode
from control_plane_kit_core.planning import PlanGraphSide
from control_plane_kit_operations.health_receiver_trust import HealthReceiverSelection, HealthReceiverTrustError
# Intentional test-only coupling: exercise the real immutable owner, not a copy.
from control_plane_kit_operations._health_receiver_trust import require_health_receiver_coverage
from fastapi.testclient import TestClient
from cpk_http_host_fixtures import token
from health_receiver_join_fixtures import document, gateway_token, signers, world
from test_http_mcp_boundaries import DeterministicVerifier, RecordingService

MODULE = "control_plane_kit_servers_cpk_server.health_receiver_adapters"


class CoverageRefused(ValueError):
    pass


class HealthReceiverAdapterTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self.clear_product_modules)
        # Build real dependencies first, so missing behavior is not a fixture/import red.
        self.world = world(self)
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "#208 real receiver adapters are missing")
        self.api = importlib.import_module(MODULE)
        from control_plane_kit_servers_cpk_server import control_configuration, server
        from control_plane_kit_servers_cpk_local_gateway import health_transit_configuration, health_transit_verification
        self.cpk, self.server = control_configuration, server
        self.gateway, self.verify = health_transit_configuration, health_transit_verification

    @staticmethod
    def clear_product_modules():
        # Preserve the existing suite's lightweight-root import isolation even
        # when the deliberate missing-behavior assertion fails during setUp.
        for name in tuple(sys.modules):
            if any(name == package or name.startswith(package + ".") for package in (
                    "control_plane_kit_servers_cpk_server", "control_plane_kit_servers_cpk_local_gateway")):
                sys.modules.pop(name, None)

    def registry(self, value=None):
        value = self.world if value is None else value
        return self.api.health_receiver_decoders(workload_documents=(value.documents["workload"],),
                                                gateway_documents=(value.documents["gateway"],))

    def selection(self, family, value=None, artifact=None, doc=None):
        value = self.world if value is None else value
        doc = value.documents[family] if doc is None else doc
        return HealthReceiverSelection("workspace-a", "revision-a", "projection-desired",
            PlanGraphSide.DESIRED_GRAPH, "cpk-a" if family == "workload" else "gateway-a",
            "runtime-a", "http-api" if family == "workload" else "http",
            ProductReference.from_document(doc), doc, value.artifacts[family] if artifact is None else artifact)

    def binding(self, registry, family, value=None):
        value = self.world if value is None else value
        purpose = (core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ if family == "workload"
                   else core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT)
        return registry.binding_for(ProductReference.from_document(value.documents[family]), purpose)

    def coverage(self, value, letter, registry=None):
        require_health_receiver_coverage(value.stores, self.registry(value) if registry is None else registry,
            plan=value.pins, graphs=value.graphs, selected=value.projected,
            workspace="workspace-a", keys=signers(value, letter), refuse=lambda:CoverageRefused("coverage refused"))

    def workload_accepts(self, value, letter):
        # Actual application host and SDK verifier; replace only unrelated database composition.
        config = self.cpk.decode_cpk_control_configuration(value.artifacts["workload"].content.encode())
        bootstrap = self.server.CpkServerBootstrapConfiguration.from_environment({
            "CPK_SERVER_MODE":"execution-capable", "CPK_PORT":"8080", "CPK_RUNTIME_INTERPRETERS":"none",
            **{f"CPK_{store}_DATABASE_URL":"postgres://fixture:fixture@database.invalid/db"
               for store in ("WORKPLACE", "ACTIVITY_HISTORY", "OBSERVER_STATE", "GRAPH_TOPOLOGY")}})
        services = {role:RecordingService(role.value) for role in core.ControlPlaneServiceRole}
        with patch.object(self.server, "_operations_application", return_value=SimpleNamespace(services=services)):
            app = self.server.create_app(bootstrap, DeterministicVerifier(), control=config, clock=lambda:150)
        with TestClient(app) as client:
            response = client.get("/__control/health/liveness",
                headers={"Authorization":"Bearer " + token(value.authorities[letter])})
        self.assertEqual([request for service in services.values() for request in service.requests], [])
        return response.status_code == 200

    def gateway_accepts(self, value, letter):
        verifier = self.verify.gateway_health_transit_verifier_from_artifact(value.artifacts["gateway"])
        credential, request = gateway_token(value, letter)
        try:
            actual = verifier.verify(credential, request, expected_attempt_id="attempt-a",
                expected_target=value.config.target, expected_runtime_id=value.config.runtime_id,
                expected_declaration=value.config.declaration, expected_kind=core.NodeHealthReadKind.LIVENESS, now=150)
        except self.verify.GatewayHealthTransitVerificationError:
            return False
        self.assertEqual(actual, request)
        return True

    def refusal(self, action):
        with self.assertRaises(HealthReceiverTrustError) as caught:
            action()
        self.assertEqual(str(caught.exception), "health receiver trust is unavailable")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(vars(caught.exception), {})

    def test_selected_bytes_and_real_verifiers_agree_with_real_coverage(self):
        for selected in ("a", "b", "ab"):
            value = world(self, selected=selected)
            registry = self.registry(value)
            for family in ("workload", "gateway"):
                decoded = self.binding(registry, family, value).decoder.decode(self.selection(family, value))
                self.assertEqual({key.key_id for key in decoded.public_keys},
                    {value.authorities[letter].config.health_keys.public_keys[0].key_id for letter in selected})
                if selected != "a":
                    self.assertNotEqual(value.artifacts[family].content_digest, value.defaults[family].content_digest)
            for letter in ("a", "b", "c"):
                with self.subTest(selected=selected, signer=letter):
                    expected = letter in selected
                    self.assertEqual(self.workload_accepts(value, letter), expected)
                    self.assertEqual(self.gateway_accepts(value, letter), expected)
                    if expected:
                        self.coverage(value, letter, registry)
                    else:
                        with self.assertRaises(CoverageRefused):
                            self.coverage(value, letter, registry)
            self.assertTrue(value.stores.registered_products.calls)

    def test_both_original_graph_sides_use_selected_bytes(self):
        for side in (PlanGraphSide.BASE_GRAPH, PlanGraphSide.DESIRED_GRAPH):
            value = world(self, side=side)
            self.assertIs(value.projected.operation.target.graph_side, side)
            if side is PlanGraphSide.BASE_GRAPH:
                self.assertNotEqual(value.graphs[0].graph.node("cpk-a").configuration_artifacts,
                                    value.graphs[1].graph.node("cpk-a").configuration_artifacts)
            self.coverage(value, "b")
            with self.assertRaises(CoverageRefused):
                self.coverage(value, "a")

    def test_complete_three_cpk_source_contracts_bind_without_ready_or_image_claim(self):
        for variant in self.cpk.CpkSourceVariant:
            doc = document(variant.value, self.cpk.cpk_source_runtime_contract(variant, self.world.defaults["workload"]))
            registry = self.api.health_receiver_decoders(workload_documents=(doc,))
            binding = registry.binding_for(ProductReference.from_document(doc), core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)
            selected = self.selection("workload", doc=doc)
            actual = binding.decoder.decode(selected)
            self.assertEqual(actual.public_keys, self.world.config.health_keys.public_keys)
            self.assertEqual(actual.target, self.world.config.target)
            self.assertEqual(len(doc.product.runtime_contract.sockets.requirements), 4)
            self.assertTrue(doc.product.runtime_contract.verification.checks)

    def test_exact_product_and_declared_slot_bindings_refuse_substitution(self):
        for family in ("workload", "gateway"):
            doc = self.world.documents[family]
            binding = self.binding(self.registry(), family)
            other = document("substituted-" + family, doc.product.runtime_contract)
            self.refusal(lambda:binding.decoder.decode(self.selection(family, doc=other)))
            kwargs = {"workload_documents" if family == "workload" else "gateway_documents":(doc, doc)}
            self.refusal(lambda:self.api.health_receiver_decoders(**kwargs))
            absent = document("missing-slot-" + family, replace(doc.product.runtime_contract, configuration_artifacts=()))
            kwargs = {"workload_documents" if family == "workload" else "gateway_documents":(absent,)}
            self.refusal(lambda:self.api.health_receiver_decoders(**kwargs))
            for change in (dict(artifact_id="other"), dict(target_path="/etc/other.json"),
                           dict(media_type=ConfigurationMediaType.TEXT),
                           dict(file_mode=ConfigurationFileMode.OWNER_READ_ONLY)):
                artifact = replace(self.world.artifacts[family], **change)
                self.refusal(lambda:binding.decoder.decode(self.selection(family, artifact=artifact)))

    def test_wrong_profile_refuses_and_configured_identity_is_not_rewritten(self):
        registry = self.registry()
        for family in ("workload", "gateway"):
            binding = self.binding(registry, family)
            chosen = self.world.artifacts[family]
            raw = json.loads(chosen.content)
            wrong = replace(chosen, content=json.dumps({**raw, "profile":"unsupported.v1"}))
            self.refusal(lambda:binding.decoder.decode(self.selection(family, artifact=wrong)))
            if family == "workload":
                raw["target"]["node_id"] = "different-node"
            else:
                raw["gateway_node_id"] = "different-node"
            changed = replace(chosen, content=json.dumps(raw))
            facts = binding.decoder.decode(self.selection(family, artifact=changed))
            identity = facts.target.node_id if family == "workload" else facts.gateway_node_id
            self.assertEqual(identity.value, "different-node")

    def test_configured_runtime_mismatch_is_refused_by_real_owner_and_receiver(self):
        for family in ("workload", "gateway"):
            value = world(self, configuration_changes={family:{"runtime_id":"different-runtime"}})
            facts = self.binding(self.registry(value), family, value).decoder.decode(self.selection(family, value))
            self.assertEqual(facts.runtime_id.value, "different-runtime")
            with self.assertRaises(CoverageRefused):
                self.coverage(value, "b")
            verify = self.workload_accepts if family == "workload" else self.gateway_accepts
            self.assertFalse(verify(value, "b"))

    def test_unexpected_decoder_and_product_owner_errors_keep_identity(self):
        value = self.world
        marker = RuntimeError("synthetic programmer failure")
        with patch.object(self.api, "decode_cpk_control_configuration", side_effect=marker):
            with self.assertRaises(RuntimeError) as caught:
                self.coverage(value, "b")
        self.assertIs(caught.exception, marker)
        owner = HealthReceiverTrustError("synthetic store owner refusal")
        with patch.object(value.stores.registered_products, "get", side_effect=owner):
            with self.assertRaises(HealthReceiverTrustError) as caught:
                self.coverage(value, "b")
        self.assertIs(caught.exception, owner)

    def test_decoding_is_pure_and_public_results_do_not_render_material(self):
        registry = self.registry()
        for family in ("workload", "gateway"):
            binding = self.binding(registry, family)
            selection = self.selection(family)
            with patch("builtins.open", side_effect=AssertionError("file effect")), \
                 patch("os.open", side_effect=AssertionError("file effect")), \
                 patch("socket.create_connection", side_effect=AssertionError("network effect")):
                facts = binding.decoder.decode(selection)
            for value in (facts, binding.decoder):
                for sensitive in ("BEGIN PUBLIC KEY", "workspace-a", "health-b"):
                    self.assertNotIn(sensitive, repr(value))
