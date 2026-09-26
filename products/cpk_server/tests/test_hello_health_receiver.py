"""Selected Hello public facts, not deployment support or lifecycle evidence."""
from dataclasses import replace
import importlib
import inspect
import json
import sys
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationFileMode, ConfigurationMediaType
from control_plane_kit_core.planning import PlanGraphSide
from control_plane_kit_core.products import ProductReference
from control_plane_kit_operations.health_receiver_trust import HealthReceiverSelection, HealthReceiverTrustError
from cpk_http_host_fixtures import fixture
from health_receiver_join_fixtures import document, world


class HelloHealthReceiverTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self.clear_modules)
        self.hello = importlib.import_module("control_plane_kit_servers_hello_server.configuration")
        self.api = importlib.import_module("control_plane_kit_servers_cpk_server.health_receiver_adapters")
        first, other = fixture(), fixture("b")
        roles = core.NodeControlGraphReferenceRole
        base = first.config
        self.config = self.hello.HelloControlConfiguration(
            target=replace(base.target,
                node_id=core.NodeControlGraphReference(roles.NODE, "hello-a"),
                provider_socket_name=core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "internal")),
            runtime_id=base.runtime_id, declaration=self.hello.hello_control_declaration(),
            surface_issuer=base.surface_issuer, surface_keys=base.surface_keys,
            health_issuer=base.health_issuer, health_keys=base.health_keys,
        )
        self.selected = replace(self.config, health_issuer="selected-health",
                                health_keys=other.config.health_keys)
        self.default_artifact = self.hello.hello_control_configuration_artifact(self.config)
        self.artifact = self.hello.hello_control_configuration_artifact(self.selected)
        self.contract = self.hello.hello_source_runtime_contract(self.default_artifact)
        self.document = document("hello-receiver-source", self.contract)
        self.assertIn("hello_documents", inspect.signature(self.api.health_receiver_decoders).parameters,
                      "the receiver registry has no Hello binding input")

    @staticmethod
    def clear_modules():
        for name in tuple(sys.modules):
            if any(name == root or name.startswith(root + ".") for root in (
                    "control_plane_kit_servers_cpk_server", "control_plane_kit_servers_cpk_local_gateway",
                    "control_plane_kit_servers_hello_server")):
                sys.modules.pop(name, None)

    def registry(self, **kwargs):
        return self.api.health_receiver_decoders(hello_documents=(self.document,), **kwargs)

    def binding(self, registry=None):
        return (self.registry() if registry is None else registry).binding_for(
            ProductReference.from_document(self.document), core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)

    def selection(self, *, artifact=None, doc=None):
        doc = self.document if doc is None else doc
        return HealthReceiverSelection("workspace-a", "revision-a", "projection-desired",
            PlanGraphSide.DESIRED_GRAPH, "hello-a", "runtime-a", "internal",
            ProductReference.from_document(doc), doc, self.artifact if artifact is None else artifact)

    def refusal(self, action):
        with self.assertRaises(HealthReceiverTrustError) as caught:
            action()
        self.assertEqual(str(caught.exception), "health receiver trust is unavailable")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(vars(caught.exception), {})

    def test_complete_source_contract_binds_selected_health_facts_and_coexists(self):
        existing = world(self)
        registry = self.registry(workload_documents=(existing.documents["workload"],),
                                 gateway_documents=(existing.documents["gateway"],))
        self.assertEqual(len(registry.bindings), 3)
        binding = self.binding(registry)
        self.assertEqual((binding.configuration_profile, binding.artifact_id, binding.target_path,
                          binding.media_type, binding.file_mode),
                         ("hello-control-configuration.v1", "hello-control", "/etc/cpk/hello/control.json",
                          ConfigurationMediaType.JSON, ConfigurationFileMode.READ_ONLY))
        actual = binding.decoder.decode(self.selection())
        self.assertEqual((actual.target, actual.runtime_id, actual.declaration),
                         (self.selected.target, self.selected.runtime_id, self.selected.declaration))
        self.assertEqual(actual.purpose, core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)
        self.assertEqual(actual.issuer, self.selected.health_issuer)
        self.assertEqual(actual.audience, core.workload_node_control_audience(self.selected.target))
        self.assertEqual(actual.public_keys, self.selected.health_keys.public_keys)
        self.assertNotEqual(actual.public_keys, self.config.health_keys.public_keys)
        self.assertNotEqual(actual.public_keys, self.selected.surface_keys.public_keys)
        self.assertEqual(self.document.product.runtime_contract.verification, self.contract.verification)
        self.assertEqual(len(self.contract.verification.checks), 2)
        for family, purpose in (("workload", core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ),
                                ("gateway", core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT)):
            self.assertIsNotNone(registry.binding_for(ProductReference.from_document(existing.documents[family]), purpose))

    def test_exact_reference_slot_and_registry_membership_fail_closed(self):
        decoder = self.binding().decoder
        other = document("other-hello", self.contract)
        self.refusal(lambda: decoder.decode(self.selection(doc=other)))
        absent = document("hello-no-slot", replace(self.contract, configuration_artifacts=()))
        self.refusal(lambda: self.api.health_receiver_decoders(hello_documents=(absent,)))
        self.refusal(lambda: self.api.health_receiver_decoders(hello_documents=(self.document, self.document)))
        self.refusal(lambda: self.api.health_receiver_decoders(hello_documents=[self.document]))
        self.refusal(lambda: self.binding(self.api.health_receiver_decoders()))
        for changes in (dict(artifact_id="cpk-control"), dict(target_path="/etc/cpk/control.json"),
                        dict(media_type=ConfigurationMediaType.TEXT),
                        dict(file_mode=ConfigurationFileMode.OWNER_READ_ONLY)):
            self.refusal(lambda: decoder.decode(self.selection(artifact=replace(self.artifact, **changes))))

    def test_configured_identity_is_reported_without_rewriting_selection(self):
        raw = json.loads(self.artifact.content)
        raw["runtime_id"] = "configured-other-runtime"
        raw["target"]["node_id"] = "configured-other-node"
        actual = self.binding().decoder.decode(self.selection(artifact=replace(self.artifact, content=json.dumps(raw))))
        self.assertEqual(actual.runtime_id.value, "configured-other-runtime")
        self.assertEqual(actual.target.node_id.value, "configured-other-node")

    def test_real_codec_refusal_is_bounded_and_detached(self):
        decoder = self.binding().decoder
        original = json.loads(self.artifact.content)
        for changes in ({"profile": "cpk-control-configuration.v1"},
                        {"health_read": {"issuer": "private-candidate-marker", "public_keys": []}},
                        {"surface_read": {"issuer": "private-candidate-marker", "public_keys": []}}):
            artifact = replace(self.artifact, content=json.dumps({**original, **changes}))
            self.refusal(lambda: decoder.decode(self.selection(artifact=artifact)))

    def test_unexpected_codec_failure_keeps_identity(self):
        marker = RuntimeError("programmer failure")
        with patch.object(self.api, "decode_hello_control_configuration", side_effect=marker):
            with self.assertRaises(RuntimeError) as caught:
                self.binding().decoder.decode(self.selection())
        self.assertIs(caught.exception, marker)

    def test_decoding_has_no_file_network_or_material_rendering(self):
        decoder, selection = self.binding().decoder, self.selection()
        with patch("builtins.open", side_effect=AssertionError("file effect")), \
             patch("os.open", side_effect=AssertionError("file effect")), \
             patch("socket.create_connection", side_effect=AssertionError("network effect")):
            actual = decoder.decode(selection)
        for value in (decoder, actual):
            for material in ("BEGIN PUBLIC KEY", "workspace-a", "selected-health"):
                self.assertNotIn(material, repr(value))
