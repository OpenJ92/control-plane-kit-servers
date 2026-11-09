"""Public root authoring laws; all keys/identities/images below are unit fixtures."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from control_plane_kit_core.configuration import ConfigurationArtifact
from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference, ProductReferenceCodec
from control_plane_kit_core.receiver_configuration import ReceiverNodeControlConfigurationCodec
from control_plane_kit_servers_cpk_server.bootstrap import _installation, plan_root_bootstrap
from control_plane_kit_servers_cpk_server.installation import _postgres_variant
from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import gateway_http_sample_declared_runtime_contract
from control_plane_kit_servers_website_server.managed import control_declaration, control_configuration_artifact
from root_complete_fixtures import complete_input
from test_managed_postgres_installation import managed_input
from test_root_bootstrap import DRIVER
from grandparent_public_root_input import prepare_root_input, ROOT, SENDER_PATH


class PublicRootInputTests(unittest.TestCase):
    def request(self):
        with TemporaryDirectory() as directory:
            base = complete_input(commissioning_directory=Path(directory))
        codec = ProductDescriptorCodec()
        artifacts = {role:codec.decode_document(base["installation"]["products"][role]).product.runtime_contract.configuration_artifacts[0]
            for role in ("cpk", "secrets")}
        control = ReceiverNodeControlConfigurationCodec().decode_bytes(artifacts["cpk"].content.encode())
        website = base["installation"].pop("website")
        base["installation"]["workspace_grants"] = []
        base["installation"]["control_auth"] = {"kind":"multi-principal",
            "principals_document":"secret://bootstrap/root-a/principals"}
        declaration = control_declaration()
        website["managed_control_configuration"] = control_configuration_artifact(replace(control,
            target=replace(control.target, node_id=replace(control.target.node_id, value="root-a-website"),
                provider_socket_name=declaration.surface.provider_socket_name, receiver_id="c" * 32),
            declaration=declaration)).descriptor()
        # Actual rendering never enters this fixture: separate synthetic child
        # material exists only to provide a valid PG sender document for the law.
        with TemporaryDirectory() as directory:
            child = _installation(managed_input(commissioning_directory=Path(directory)))
        pg = codec.encode_document(_postgres_variant(child))
        gateway = codec.decode_document((ROOT / "products/cpk_local_gateway/product.cpk.json").read_bytes())
        gateway = codec.encode_document(replace(gateway.product, runtime_contract=gateway_http_sample_declared_runtime_contract()))
        sender = json.dumps({"schema":"cpk-server.managed-verification.v1",
            "gateway_product":ProductReferenceCodec().encode(ProductReference.from_document(gateway)),
            "postgres_product_document":pg.content.decode()}, sort_keys=True, separators=(",", ":"))
        raw = json.dumps({"schema":"cpk.root-commissioning.public.v1", "artifacts":{
            role:artifact.descriptor() for role, artifact in artifacts.items()}, "receiver_ids":{
                role:ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode()).target.receiver_id
                for role, artifact in artifacts.items()}})
        return {"base_input":base, "parent_public_document":raw, "parent_public_sha256":sha256(raw.encode()).hexdigest(),
            "cpk_image":child.cpk_product.product.image.descriptor(),
            "secrets_image":child.secrets_product.product.image.descriptor(),
            "connector_image":gateway.product.image.descriptor(),
            "gateway_document":gateway.content.decode(), "gateway_sha256":gateway.content_digest,
            "sender_document":sender, "sender_sha256":sha256(sender.encode()).hexdigest(),
            "website":website, "capability_ids":["unit-parent-management"]}

    def test_public_preprojection_preserves_normal_plan_artifacts_and_parent_stock_database(self):
        request = self.request()
        with patch("control_plane_kit_servers_cpk_server.root_commissioning.prepare_root_commissioning",
                side_effect=AssertionError("private preparation entered")):
            actual = prepare_root_input(request)
        item = actual["installation"]
        self.assertNotIn("workspace_authority", item)
        self.assertEqual(item["workspace_grants"], [])
        self.assertEqual(item["control_auth"], request["base_input"]["installation"]["control_auth"])
        self.assertEqual(item["products"]["postgres"], request["base_input"]["installation"]["products"]["postgres"])
        self.assertEqual(actual["setup"], request["base_input"]["setup"])
        self.assertEqual(item["website"], request["website"])
        # Unit-only commitment: actual metadata must wait for Vale's real owner.
        projected = deepcopy(actual)
        projected["installation"]["workspace_grants"] = []
        projected["installation"]["workspace_authority"] = {"mode":"dynamic-v1", "private_intent_sha256":"d" * 64}
        projected["setup"]["administration"] = {"permission_grant_count":3, "management_grant":False}
        plan = plan_root_bootstrap(projected, driver_image_id=DRIVER)
        cpk = next(node for node in plan["resources"]["nodes"] if node["node_id"] == "root-a-cpk")
        files = {entry["artifact"]["target_path"]:entry["artifact"] for entry in cpk["configuration_files"]}
        self.assertEqual(files[SENDER_PATH]["content"], request["sender_document"])
        self.assertEqual(cpk["environment"]["CPK_MANAGED_VERIFICATION_CONFIGURATION_FILE"], SENDER_PATH)
        self.assertEqual(cpk["environment"]["CPK_MANAGED_HEALTH"], "docker-unix-v2")
        health = json.loads(item["managed_health_configuration"]["content"])
        from control_plane_kit_servers_cpk_server.managed_health_configuration import managed_health_configuration_artifact
        # Static artifact authoring keeps rejecting v2; this renderer explicitly
        # selects the existing dynamic admission owner.
        with self.assertRaises(ValueError):
            managed_health_configuration_artifact(item["managed_health_configuration"]["content"].encode())
        self.assertEqual(health["gateway_documents"], [request["gateway_document"]])
        self.assertEqual(health["capability_ids"], request["capability_ids"])
        website = next(node for node in plan["resources"]["nodes"] if node["node_id"] == "root-a-website")
        self.assertEqual(website["environment"]["CPK_WEB_UPSTREAM"], item["external_endpoint"])

    def test_crossed_public_inputs_and_reused_parent_receiver_refuse(self):
        request = self.request()
        for field in ("parent_public_sha256", "gateway_sha256", "sender_sha256"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                prepare_root_input(request | {field:"0" * 64})
        changed = deepcopy(request)
        changed["base_input"]["installation"]["workspace_id"] = "foreign-child"
        with self.assertRaises(ValueError):
            prepare_root_input(changed)
        changed = deepcopy(request)
        artifact = ConfigurationArtifact.from_descriptor(changed["website"]["managed_control_configuration"])
        codec = ReceiverNodeControlConfigurationCodec()
        web = codec.decode_bytes(artifact.content.encode())
        public = json.loads(changed["parent_public_document"])
        web = replace(web, target=replace(web.target, receiver_id=public["receiver_ids"]["cpk"]))
        changed["website"]["managed_control_configuration"] = replace(artifact, content=codec.encode_bytes(web).decode()).descriptor()
        with self.assertRaises(ValueError):
            prepare_root_input(changed)
