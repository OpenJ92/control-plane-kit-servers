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
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.products import ProductReference
from control_plane_kit_core.configuration import ConfigurationMediaType, ConfigurationFileMode
from control_plane_kit_core.planning import PlanGraphSide
from control_plane_kit_operations.health_receiver_trust import HealthReceiverSelection, HealthReceiverTrustError
# Intentional test-only coupling: exercise the real immutable owner, not a copy.
from control_plane_kit_operations._health_receiver_trust import require_health_receiver_coverage
from fastapi.testclient import TestClient
from cpk_http_host_fixtures import token
from health_receiver_join_fixtures import document, gateway_token, gateway_self_world, signers, world
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


class GatewaySelfHealthAdapterTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(HealthReceiverAdapterTests.clear_product_modules)
        self.value = gateway_self_world()
        self.api = importlib.import_module(MODULE)
        self.decoder_type = getattr(self.api, "GatewaySelfHealthReceiverDecoder", None)
        self.assertIsNotNone(self.decoder_type, "#219 gateway self receiver decoder is missing")
        self.select = getattr(self.api, "select_gateway_self_health_binding", None)
        self.assertIsNotNone(self.select, "#219 selected self binding projection is missing")

    refusal = HealthReceiverAdapterTests.refusal

    def selection(self, family, *, artifact=None, doc=None, **changes):
        value = self.value
        doc = value.document if doc is None else doc
        selected = HealthReceiverSelection("workspace-a", "revision-a", "projection-desired",
            PlanGraphSide.DESIRED_GRAPH, "gateway-a", "runtime-a", "control",
            ProductReference.from_document(doc), doc, value.artifacts[family] if artifact is None else artifact)
        return replace(selected, **changes)

    def selections(self):
        return {family:self.selection(family) for family in ("transit", "targets", "control")}

    def decoder(self, doc=None):
        return self.decoder_type(ProductReference.from_document(self.value.document if doc is None else doc))

    def changed(self, family, change):
        artifact = self.value.artifacts[family]
        raw = json.loads(artifact.content)
        change(raw)
        return replace(artifact, content=json.dumps(raw))

    def test_actual_source_contract_dual_purpose_and_selected_keys(self):
        value = self.value
        reference = ProductReference.from_document(value.document)
        self.assertEqual(value.registered.get("workspace-a", reference).descriptor_document, value.document)
        registry = self.api.health_receiver_decoders(gateway_documents=(value.document,),
            gateway_self_documents=(value.document,))
        for family, purpose in (("transit", core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT),
                                ("control", core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)):
            with self.subTest(family=family):
                binding = registry.binding_for(reference, purpose)
                decoded = binding.decoder.decode(self.selection(family))
                self.assertIs(decoded.purpose, purpose)
                self.assertEqual(decoded.public_keys, value.config.health_keys.public_keys)
                self.assertEqual([key.key_id for key in decoded.public_keys], ["health-b"])
                self.assertNotEqual(value.artifacts[family].content_digest, value.defaults[family].content_digest)
        self.assertEqual(self.decoder().decode(self.selection("control")).declaration, value.config.declaration)
        self.refusal(lambda:registry.binding_for(reference, core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ))
        transit_only = self.api.health_receiver_decoders(gateway_documents=(value.document,))
        self.refusal(lambda:transit_only.binding_for(reference, core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ))
        self.refusal(lambda:self.api.health_receiver_decoders().binding_for(reference, core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ))

    def test_actual_self_alias_and_selected_target_bytes_are_preserved(self):
        selected = self.selections()
        actual = self.select(**selected)
        self.assertEqual(actual, self.value.binding)
        self.assertEqual(actual.target_id, "unrelated-alias-73")
        self.assertEqual(actual.origin, "http://private-origin-canary:8000")
        changed = self.changed("targets", lambda raw:raw["targets"][0].update(target_id="other-installed-alias"))
        self.assertNotEqual(changed.content_digest, self.value.defaults["targets"].content_digest)
        selected["targets"] = self.selection("targets", artifact=changed)
        self.assertEqual(self.select(**selected).target_id, "other-installed-alias")
        for side in PlanGraphSide:
            self.assertEqual(self.select(**{name:replace(value, graph_side=side) for name,value in selected.items()}).target_id,
                             "other-installed-alias")

    def test_self_decoder_refuses_selected_context_and_declared_surface_mismatch(self):
        decoder = self.decoder()
        for name in ("workspace_id", "authored_graph_id", "receiver_node_id", "runtime_id", "provider_socket_name"):
            with self.subTest(name=name):
                self.refusal(lambda:decoder.decode(self.selection("control", **{name:"foreign"})))
        contract = self.value.contract
        for surfaces in ((), (replace(contract.control_surfaces[0], health_reads=(core.NodeHealthReadKind.LIVENESS,)),)):
            capabilities = contract.capabilities if surfaces else tuple(
                value for value in contract.capabilities if value is not CapabilityName.NODE_CONTROLLABLE)
            doc = document("different-own-surface", replace(contract, control_surfaces=surfaces, capabilities=capabilities))
            self.refusal(lambda:self.decoder(doc).decode(self.selection("control", doc=doc)))
        # Valid selected configuration with a foreign full target must not be
        # treated as the registered default or rewritten to selection truth.
        for key in ("workspace_id", "graph_revision", "node_id"):
            artifact = self.changed("control", lambda raw:raw["target"].update({key:"foreign"}))
            self.refusal(lambda:decoder.decode(self.selection("control", artifact=artifact)))
        artifact = self.changed("control", lambda raw:raw.update(runtime_id="foreign"))
        self.refusal(lambda:decoder.decode(self.selection("control", artifact=artifact)))

    def test_all_three_selections_require_same_provenance_and_selected_transit_socket(self):
        for family in ("transit", "targets", "control"):
            for name in ("workspace_id", "authored_graph_id", "realized_projection_id", "receiver_node_id", "runtime_id", "provider_socket_name"):
                selected = self.selections()
                selected[family] = replace(selected[family], **{name:"foreign"})
                with self.subTest(family=family, name=name):
                    self.refusal(lambda:self.select(**selected))
            selected = self.selections()
            selected[family] = replace(selected[family], graph_side=PlanGraphSide.BASE_GRAPH)
            self.refusal(lambda:self.select(**selected))
            doc = document("foreign-product", self.value.contract)
            selected[family] = self.selection(family, doc=doc)
            self.refusal(lambda:self.select(**selected))

    def test_wrong_slots_profiles_and_missing_registered_slot_refuse(self):
        for family in ("transit", "targets", "control"):
            for changes in ({"artifact_id":"foreign"}, {"target_path":"/etc/foreign.json"},
                            {"media_type":ConfigurationMediaType.TEXT}, {"file_mode":ConfigurationFileMode.OWNER_READ_ONLY}):
                selected = self.selections()
                selected[family] = self.selection(family, artifact=replace(self.value.artifacts[family], **changes))
                self.refusal(lambda:self.select(**selected))
            selected = self.selections()
            selected[family] = self.selection(family, artifact=self.changed(family, lambda raw:raw.update(profile="foreign.v1")))
            self.refusal(lambda:self.select(**selected))
            missing = document("missing-slot", replace(self.value.contract, configuration_artifacts=tuple(
                value for value in self.value.contract.configuration_artifacts if value.artifact_id != self.value.artifacts[family].artifact_id)))
            self.refusal(lambda:self.select(**{name:self.selection(name, doc=missing) for name in self.selections()}))
        wrong = document("wrong-product", self.value.contract)
        self.refusal(lambda:self.decoder().decode(self.selection("control", doc=wrong)))
        self.refusal(lambda:self.api.health_receiver_decoders(gateway_self_documents=(self.value.document, self.value.document)))

    def test_missing_foreign_and_duplicate_self_bindings_use_actual_codec_refusals(self):
        changes = [lambda raw:raw.update(targets=[]),
            lambda raw:raw["targets"][0]["target"].update(graph_revision="foreign"),
            lambda raw:raw["targets"][0]["target"].update(node_id="foreign"),
            lambda raw:raw["targets"][0].update(runtime_id="foreign"),
            lambda raw:raw["targets"].append(dict(raw["targets"][0])),
            lambda raw:raw["targets"].append({**raw["targets"][0], "target_id":"second-alias"})]
        for change in changes:
            selected = self.selections()
            selected["targets"] = self.selection("targets", artifact=self.changed("targets", change))
            self.refusal(lambda:self.select(**selected))
        for family in ("transit", "targets"):
            selected = self.selections()
            selected[family] = self.selection(family, artifact=self.changed(family, lambda raw:raw.update(gateway_node_id="foreign")))
            self.refusal(lambda:self.select(**selected))

    def test_pure_selection_and_bounded_candidate_free_errors(self):
        selected = self.selections()
        with patch("builtins.open", side_effect=AssertionError("file effect")), \
             patch("os.open", side_effect=AssertionError("file effect")), \
             patch("socket.create_connection", side_effect=AssertionError("network effect")):
            self.assertEqual(self.select(**selected), self.value.binding)
            facts = self.decoder().decode(selected["control"])
        for value in (facts, self.decoder()):
            self.assertNotIn("BEGIN PUBLIC KEY", repr(value))
        selected["targets"] = self.selection("targets", artifact=self.changed("targets",
            lambda raw:raw.update(extra="PRIVATE-CONFIG-CANARY" * 100)))
        self.refusal(lambda:self.select(**selected))
        selected["control"] = self.selection("control", artifact=self.changed("control",
            lambda raw:raw["surface_read"].update(public_keys=[])))
        self.refusal(lambda:self.decoder().decode(selected["control"]))

    def test_unexpected_new_decoder_and_selector_errors_keep_owner_identity(self):
        selected = self.selections()
        marker = RuntimeError("synthetic owner failure")
        # Patch the selected product-codec boundary, not a parallel decoder.
        with patch.object(self.api, "decode_gateway_control_configuration", side_effect=marker):
            for action in (lambda:self.decoder().decode(selected["control"]), lambda:self.select(**selected)):
                with self.assertRaises(RuntimeError) as caught:
                    action()
                self.assertIs(caught.exception, marker)
        with patch.object(self.api, "decode_gateway_health_relay_configuration", side_effect=marker):
            with self.assertRaises(RuntimeError) as caught:
                self.select(**selected)
            self.assertIs(caught.exception, marker)
