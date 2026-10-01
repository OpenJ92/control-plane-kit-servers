"""Hello uses common selected receiver facts, not a product decoder registry."""
from dataclasses import replace
import importlib
import json
import sys
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.planning import PlanGraphSide
from control_plane_kit_core.products import ProductReference
from control_plane_kit_operations.health_receiver_trust import HealthReceiverSelection, HealthReceiverTrustError
from cpk_http_host_fixtures import fixture, verifier_family, with_health
from health_receiver_join_fixtures import document, world


class HelloHealthReceiverTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self.clear_modules)
        self.hello = importlib.import_module("control_plane_kit_servers_hello_server.configuration")
        self.api = importlib.import_module("control_plane_kit_servers_cpk_server.health_receiver_adapters")
        first, other = fixture(), fixture("b")
        roles = core.NodeControlGraphReferenceRole
        base = first.config
        self.config = core.ReceiverNodeControlConfiguration(
            target=replace(base.target,
                node_id=core.NodeControlGraphReference(roles.NODE, "hello-a"),
                provider_socket_name=core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "internal")),
            declaration=self.hello.hello_control_declaration(), verifiers=base.verifiers)
        self.selected = with_health(self.config, issuer="selected-health", public_keys=verifier_family(other.config).public_keys)
        self.default_artifact = self.hello.hello_control_configuration_artifact(self.config)
        self.artifact = self.hello.hello_control_configuration_artifact(self.selected)
        self.contract = self.hello.hello_source_runtime_contract(self.default_artifact)
        self.document = document("hello-receiver-source", self.contract)

    @staticmethod
    def clear_modules():
        for name in tuple(sys.modules):
            if any(name == root or name.startswith(root + ".") for root in (
                    "control_plane_kit_servers_cpk_server", "control_plane_kit_servers_cpk_local_gateway",
                    "control_plane_kit_servers_hello_server")):
                sys.modules.pop(name, None)

    def selection(self, *, artifact=None, doc=None):
        doc = self.document if doc is None else doc
        return HealthReceiverSelection("workspace-a", "revision-a", "projection-desired",
            PlanGraphSide.DESIRED_GRAPH, "hello-a", "runtime-a", "internal",
            ProductReference.from_document(doc), doc, self.artifact if artifact is None else artifact)

    def decode(self, selection=None):
        return self.api.select_own_health_configuration(self.selection() if selection is None else selection)

    def refusal(self, action):
        with self.assertRaises(HealthReceiverTrustError) as caught:
            action()
        self.assertEqual(str(caught.exception), "health receiver trust is unavailable")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(vars(caught.exception), {})

    def test_complete_source_contract_binds_selected_health_facts_and_coexists(self):
        existing = world(self)
        registry = self.api.health_receiver_decoders(gateway_documents=(existing.documents["gateway"],))
        self.assertEqual(len(registry.bindings), 1)
        actual = self.decode()
        self.assertIs(type(actual), core.ReceiverNodeControlConfiguration)
        self.assertEqual(actual, self.selected)
        family = verifier_family(actual)
        self.assertEqual(family.issuer, "selected-health")
        self.assertEqual(family.public_keys, verifier_family(self.selected).public_keys)
        self.assertNotEqual(family.public_keys, verifier_family(self.config).public_keys)
        self.assertNotEqual(family.public_keys, verifier_family(self.selected,
            core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ).public_keys)
        self.assertEqual(self.document.product.runtime_contract.verification, self.contract.verification)
        self.assertEqual(len(self.contract.verification.checks), 2)
        self.assertIsNotNone(registry.binding_for(ProductReference.from_document(existing.documents["gateway"]),
            core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT))
        self.refusal(lambda:registry.binding_for(ProductReference.from_document(self.document),
            core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ))

    def test_exact_reference_slot_and_registry_membership_fail_closed(self):
        other = document("other-hello", self.contract)
        forged = replace(self.selection())
        object.__setattr__(forged, "descriptor_document", other)
        self.refusal(lambda:self.decode(forged))
        absent = document("hello-no-slot", replace(self.contract, configuration_artifacts=()))
        self.refusal(lambda:self.decode(self.selection(doc=absent)))
        # Own-health needs no registration; descriptor-selected material is still exact.
        self.assertEqual(self.decode(), self.selected)
        for changes in (dict(artifact_id="cpk-control"), dict(target_path="/etc/cpk/control.json"),
                        dict(media_type=ConfigurationMediaType.TEXT), dict(file_mode=ConfigurationFileMode.OWNER_READ_ONLY)):
            self.refusal(lambda:self.decode(self.selection(artifact=replace(self.artifact, **changes))))

    def test_configured_identity_is_reported_without_rewriting_selection(self):
        raw = json.loads(self.artifact.content)
        raw["target"]["runtime_id"] = "configured-other-runtime"
        raw["target"]["node_id"] = "configured-other-node"
        artifact = replace(self.artifact, content=json.dumps(raw))
        # The common selected adapter now refuses foreign scope instead of returning
        # a product trust record for a separate later comparison.
        self.refusal(lambda:self.decode(self.selection(artifact=artifact)))
        self.assertEqual(self.decode(replace(self.selection(), authored_graph_id="revision-b",
            realized_projection_id="projection-b")), self.selected)

    def test_real_codec_refusal_is_bounded_and_detached(self):
        original = json.loads(self.artifact.content)
        invalid = [{**original, "profile":"hello-control-configuration.v1"}]
        for index in range(len(original["verifiers"])):
            families = [dict(item) for item in original["verifiers"]]
            families[index].update(issuer="private-candidate-marker", public_keys=[])
            invalid.append({**original, "verifiers":families})
        for raw in invalid:
            artifact = replace(self.artifact, content=json.dumps(raw))
            self.refusal(lambda:self.decode(self.selection(artifact=artifact)))

    def test_unexpected_codec_failure_keeps_identity(self):
        marker = RuntimeError("programmer failure")
        with patch.object(core.ReceiverNodeControlConfigurationCodec, "decode_bytes", side_effect=marker):
            with self.assertRaises(RuntimeError) as caught:
                self.decode()
        self.assertIs(caught.exception, marker)

    def test_decoding_has_no_file_network_or_material_rendering(self):
        selection = self.selection()
        with patch("builtins.open", side_effect=AssertionError("file effect")), \
             patch("os.open", side_effect=AssertionError("file effect")), \
             patch("socket.create_connection", side_effect=AssertionError("network effect")):
            actual = self.decode(selection)
        for material in ("BEGIN PUBLIC KEY", "workspace-a", "selected-health"):
            self.assertNotIn(material, repr(actual))
