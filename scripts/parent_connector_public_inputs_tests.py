"""Public-only adapter laws; generated signing material exists only in fixtures."""
from dataclasses import replace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from control_plane_kit_core.receiver_configuration import ReceiverNodeControlConfigurationCodec
from control_plane_kit_servers_cloudflared_connector import managed
import http_sample_installation_tests as installation_tests
from http_sample_installation_assembly import assemble
import http_sample_image_inputs as inputs


class ParentConnectorPublicInputTests(unittest.TestCase):
    def request(self):
        with installation_tests.isolated_directory():
            fixture, original, baseline, _, _, _ = assemble()
        parent = fixture.receiver(baseline.node(original.cpk_node_id))
        artifact, = original.cpk_product.product.runtime_contract.configuration_artifacts
        raw = json.dumps({"schema":"cpk.root-commissioning.public.v1",
            "artifacts":{"cpk":artifact.descriptor()},
            "receiver_ids":{"cpk":parent.target.receiver_id}})
        return dict(commissioning_public_document=raw,
            commissioning_public_sha256=sha256(raw.encode()).hexdigest(),
            installation_id=original.installation_id, workspace_id=original.workspace_id), parent

    def images(self):
        return installation_tests.FullInstallationHttpSampleTests().images()

    def test_two_public_configurations_equal_product_renderer_with_parent_trust(self):
        value, parent = self.request()
        receivers = {"api":"a" * 32, "website":"b" * 32}
        with patch("http_sample_installation_assembly.InstallationManagementTests.setUp",
                side_effect=AssertionError("fixture entered")), \
                patch("control_plane_kit_servers_cpk_server.root_commissioning.prepare_root_commissioning",
                    side_effect=AssertionError("private preparation entered")):
            result = inputs.parent_connector_inputs(self.images(), value, receiver_ids=receivers)
        self.assertEqual(result["schema"], "cpk.parent-connector-public-inputs.v1")
        self.assertEqual(result["image"], self.images()["connector"].descriptor())
        self.assertEqual(set(result["routes"]), {"api", "website"})
        declaration = managed.control_declaration()
        for role, artifact in result["routes"].items():
            target = replace(parent.target,
                node_id=replace(parent.target.node_id, value=value["installation_id"] + "-external-" + role + "-01"),
                provider_socket_name=declaration.surface.provider_socket_name, receiver_id=receivers[role])
            expected = managed.control_configuration_artifact(replace(parent,
                target=target, declaration=declaration))
            self.assertEqual(artifact, expected.descriptor())
            decoded = ReceiverNodeControlConfigurationCodec().decode_bytes(artifact["content"].encode())
            self.assertEqual(decoded.verifiers, parent.verifiers)
            self.assertEqual(artifact["target_path"], "/etc/cpk/cloudflared/control.json")
            self.assertEqual(artifact["file_mode"], "0444")

    def test_aliases_foreign_scope_tampered_hash_and_unsupported_roles_refuse(self):
        value, parent = self.request()
        receivers = {"api":"a" * 32, "website":"b" * 32}
        cases = [(value, {"api":"a" * 32, "website":"a" * 32}),
            (value, receivers | {"api":parent.target.receiver_id}),
            (value, {"api":"a" * 32}), (value, receivers | {"other":"c" * 32}),
            (value, receivers | {"api":"invalid"}),
            (value | {"workspace_id":"foreign"}, receivers),
            (value | {"commissioning_public_sha256":"0" * 64}, receivers),
            (value | {"extra":"ignored"}, receivers)]
        for candidate, ids in cases:
            with self.subTest(candidate=set(candidate), receivers=ids), self.assertRaises(ValueError):
                inputs.parent_connector_inputs(self.images(), candidate, receiver_ids=ids)
