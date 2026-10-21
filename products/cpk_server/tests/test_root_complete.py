"""#302 optional complete-root plan laws over actual product contracts."""
from contextlib import ExitStack
import copy
from hashlib import sha256
import importlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.topology import GraphDescriptorCodec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from root_complete_fixtures import complete_input, contract, replace_artifact_content
from test_root_bootstrap import DRIVER, installation_input


class CompleteRootPlanTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")
        self.document = complete_input()

    def plan(self, document=None):
        try:
            return self.api.plan_root_bootstrap(self.document if document is None else document,
                driver_image_id=DRIVER)
        except self.api.RootBootstrapError:
            self.fail("reviewed complete-root public input is not admitted")

    def refused(self, document):
        with self.assertRaises(self.api.RootBootstrapError):
            self.api.plan_root_bootstrap(document, driver_image_id=DRIVER)

    def test_enabled_plan_is_pure_four_node_topology_with_exact_derived_setup_product(self):
        with ExitStack() as stack:
            effects = [stack.enter_context(patch(target, side_effect=AssertionError("unexpected effect")))
                for target in ("uuid.uuid4", "os.open", "socket.socket")]
            generate = stack.enter_context(patch.object(Ed25519PrivateKey, "generate",
                side_effect=AssertionError("unexpected key generation")))
            plan = self.plan()
            self.assertEqual(plan, self.plan())
            for effect in (*effects, generate): effect.assert_not_called()
        graph = GraphDescriptorCodec().decode(plan["graph"])
        self.assertEqual(set(graph.nodes), {"root-a-cpk", "root-a-postgres", "root-a-secrets", "root-a-website"})
        self.assertEqual(graph.public_ingresses, ())
        self.assertEqual(plan["website_node_id"], "root-a-website")
        self.assertEqual(plan["host_bindings"], [
            {"node_id": "root-a-cpk", "provider_socket": "http-api", "container_port": 8080,
             "address": "127.0.0.1", "port": 18080},
            {"node_id": "root-a-website", "provider_socket": "http", "container_port": 8080,
             "address": "127.0.0.1", "port": 18081}])
        codec = ProductDescriptorCodec()
        frontend = importlib.import_module("control_plane_kit_servers_cpk_server.client.frontend")
        from control_plane_kit_core.products import OciImageReferenceCodec
        expected = json.loads(codec.encode_document(frontend.frontend_product(
            OciImageReferenceCodec().decode(self.document["installation"]["website"]["image"]),
            upstream=self.document["installation"]["external_endpoint"])).content)
        backends = json.loads(self.api.canonical(self.document))["installation"]["products"]
        self.assertEqual(plan["setup_products"], [*backends.values(), expected])
        self.assertEqual(plan["setup_routes"].count("command.product.import"), 4)
        site = next(node for node in plan["resources"]["nodes"] if node["node_id"] == "root-a-website")
        self.assertIsNone(site["local_docker_access"])
        self.assertEqual(site["secret_files"], [])
        self.assertEqual(site["http_checks"], [])
        baseline = copy.deepcopy(self.document)
        del baseline["installation"]["website"]
        self.assertEqual(plan["required_material"], self.plan(baseline)["required_material"])

    def test_absent_profile_keeps_old_fields_roundtrip_and_lazy_imports(self):
        old = installation_input()
        plan = self.plan(old)
        self.assertFalse({"website_node_id", "host_bindings", "setup_products"} & set(plan))
        self.assertEqual(len(plan["resources"]["nodes"]), 3)
        self.assertEqual(plan["setup_routes"].count("command.product.import"), 3)
        self.assertEqual(self.api.canonical(plan), self.api.canonical(self.api.verified_plan(
            json.loads(self.api.canonical(plan)), plan["digest"], DRIVER)))
        script = '''
import json,sys
from control_plane_kit_servers_cpk_server.bootstrap import plan_root_bootstrap
plan_root_bootstrap(json.loads(sys.stdin.read()), driver_image_id="sha256:"+"a"*64)
assert "control_plane_kit_servers_cpk_server.client.frontend" not in sys.modules
assert "control_plane_kit_servers_cpk_server.control_configuration" not in sys.modules
assert "control_plane_kit_secrets.control" not in sys.modules
assert "control_plane_kit_interpreters.docker" not in sys.modules
'''
        result = subprocess.run([sys.executable, "-c", script], input=json.dumps(old),
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, "absent profile imported optional owners")

    def test_website_input_is_closed_typed_and_exact_loopback(self):
        self.plan()
        site = self.document["installation"]["website"]
        candidates = [None, "website", {}, {**site, "upstream": "https://foreign.example.test"}]
        candidates += [{name: value for name, value in site.items() if name != missing} for missing in site]
        candidates += [{**site, "image": value} for value in (None, "sha256:" + "a" * 64, {})]
        candidates += [{**site, "external_endpoint": value} for value in
            ("http://web.example.test", "https://root.example.test", "https://web.example.test/path")]
        candidates += [{**site, "host_binding": value} for value in (None, {},
            {"address": "0.0.0.0", "port": 18081}, {"address": "127.0.0.1", "port": 18080},
            {"address": "127.0.0.1", "port": True}, {"address": "127.0.0.1", "port": 1023},
            {"address": "127.0.0.1", "port": 65536}, {"address": "127.0.0.1", "port": "18081"},
            {"address": "127.0.0.1", "port": 18081, "container_port": 9000})]
        for site in candidates:
            with self.subTest(site=site):
                changed = copy.deepcopy(self.document)
                changed["installation"]["website"] = site
                self.refused(changed)

    def test_public_artifact_bytes_source_digests_and_receiver_ids_are_preserved(self):
        plan = self.plan()
        for role in ("cpk", "secrets"):
            expected = contract(self.document, role)["configuration_artifacts"][0]
            node = next(node for node in plan["resources"]["nodes"] if node["node_id"] == "root-a-" + role)
            entry, = node["configuration_files"]
            self.assertEqual(entry["artifact"], expected)
            self.assertEqual(entry["sha256"], sha256(expected["content"].encode()).hexdigest())
            self.assertEqual(entry["artifact"]["source_digest"], "b" * 64)
        self.assertNotIn("PRIVATE KEY", json.dumps(plan))

    def test_missing_ambiguous_wrong_slot_media_mode_digest_or_oversize_refuses(self):
        self.plan()
        for role in ("cpk", "secrets"):
            base = contract(self.document, role)["configuration_artifacts"][0]
            candidates = [[], [base, {**base, "artifact_id": "other-control"}],
                [base, {**base, "target_path": "/etc/cpk/other.json"}]]
            for field, value in (("artifact_id", "wrong-control"), ("target_path", "/etc/cpk/wrong.json"),
                    ("media_type", "text/plain"), ("file_mode", "0400"), ("content_digest", "0" * 64)):
                candidates.append([{**base, field: value}])
            from dataclasses import replace
            from control_plane_kit_core.configuration import ConfigurationArtifact
            oversized = replace(ConfigurationArtifact.from_descriptor(base), content=base["content"] + " " * 65536)
            candidates.append([oversized.descriptor()])
            for artifacts in candidates:
                with self.subTest(role=role, count=len(artifacts)):
                    changed = copy.deepcopy(self.document)
                    contract(changed, role)["configuration_artifacts"] = artifacts
                    self.refused(changed)

    def test_role_coordinates_distinct_receivers_and_actual_product_declarations_are_required(self):
        self.plan()
        for role in ("cpk", "secrets"):
            for field, value in (("workspace_id", "other-workspace"), ("runtime_id", "other-runtime"),
                    ("node_id", "other-node"), ("provider_socket_name", "other-socket")):
                changed = copy.deepcopy(self.document)
                replace_artifact_content(changed, role, lambda content: content["target"].update({field: value}))
                self.refused(changed)
            for mutate in (lambda content: content.update(verifiers=[]),
                    lambda content: content.update(profile="workload-node-control-configuration.v1"),
                    lambda content: content["declaration"].update(profile="invalid")):
                changed = copy.deepcopy(self.document)
                replace_artifact_content(changed, role, mutate)
                self.refused(changed)
        changed = copy.deepcopy(self.document)
        cpk_id = json.loads(contract(changed, "cpk")["configuration_artifacts"][0]["content"])["target"]["receiver_id"]
        replace_artifact_content(changed, "secrets", lambda content: content["target"].update(receiver_id=cpk_id))
        self.refused(changed)
        changed = copy.deepcopy(self.document)
        a, b = contract(changed, "cpk"), contract(changed, "secrets")
        a["configuration_artifacts"], b["configuration_artifacts"] = b["configuration_artifacts"], a["configuration_artifacts"]
        self.refused(changed)

    def test_wrapper_environment_and_surface_must_match_actual_public_configuration(self):
        self.plan()
        for role in ("cpk", "secrets"):
            for field, value in (("public_environment", []), ("control_surfaces", [])):
                changed = copy.deepcopy(self.document)
                contract(changed, role)[field] = value
                self.refused(changed)

    def test_plan_digest_binds_both_origins_image_bindings_and_control_bytes(self):
        plan = self.plan()
        mutations = [lambda d: d["installation"]["website"].update(external_endpoint="https://changed.example.test"),
            lambda d: d["installation"].update(external_endpoint="https://changed-api.example.test"),
            lambda d: d["installation"]["website"]["image"].update(digest="sha256:" + "b" * 64),
            lambda d: d["installation"]["website"]["host_binding"].update(port=18082),
            lambda d: d["host_binding"].update(port=18083),
            lambda d: replace_artifact_content(d, "cpk", lambda c: c["target"].update(receiver_id="c" * 32))]
        for mutate in mutations:
            changed = copy.deepcopy(self.document)
            mutate(changed)
            self.assertNotEqual(self.plan(changed)["digest"], plan["digest"])

    def test_saved_complete_plan_drift_refuses_before_material_or_state_effects(self):
        plan = self.plan()
        for field in ("host_bindings", "setup_products", "website_node_id", "graph", "setup_routes"):
            changed = copy.deepcopy(plan)
            changed[field] = [] if field != "website_node_id" else "foreign-website"
            with self.subTest(field=field), TemporaryDirectory() as directory:
                state = Path(directory) / "state"
                with self.assertRaises(self.api.RootBootstrapError):
                    self.api.apply_root_bootstrap(changed, expected_digest=plan["digest"], driver_image_id=DRIVER,
                        index_path=Path(directory) / "absent", state_directory=state)
                self.assertFalse(state.exists())
