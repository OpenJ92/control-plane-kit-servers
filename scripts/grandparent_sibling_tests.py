"""Synthetic public input composition against the actual frozen installer."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import grandparent_sibling_prepare as sibling


class SiblingPublicPreparation(unittest.TestCase):
    def setUp(self):
        import control_plane_kit_servers_cpk_server.root_commissioning as commission
        self.assertFalse(commission.__file__.startswith("/source/"))
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        self.plan = commission.plan_root_commissioning(sibling.commissioning_intent(), preparer_image_id=sibling.DRIVER)
        # Fixed public test fixture; never generate keys or open real custody.
        keys = {purpose: Ed25519PrivateKey.from_private_bytes(bytes([i + 1]) * 32)
            for i, purpose in enumerate(commission.PURPOSE_FILES)}
        ids = {"cpk": "1" * 32, "secrets": "2" * 32}
        self.public = commission._render(self.plan, ids, keys,
            {purpose: "synthetic-" + str(i) for i, purpose in enumerate(keys)})
        self.raw = sibling.canonical(self.public)
        self.completion = commission._completion(self.plan, ids, self.raw)
        postgres = json.loads(Path("/source/products/postgres_server/product.cpk.json").read_bytes())
        self.template = sibling.material_template(postgres)
        self.assertEqual(json.loads(Path("/source/docs/sibling399/commissioning-intent.json").read_bytes()),
            sibling.commissioning_intent())
        self.assertEqual(json.loads(Path("/source/docs/sibling399/material-template.json").read_bytes()), self.template)

    def bind(self):
        return sibling.bind_material(self.template, self.plan, self.raw, self.completion)

    def test_normal_frozen_material_owner_compiles_fresh_three_node_read_scope(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from control_plane_kit_servers_cpk_server.bootstrap import verified_plan
        with patch.object(Ed25519PrivateKey, "generate", side_effect=AssertionError("generation")) as generate, \
                patch("socket.socket", side_effect=AssertionError("network")), \
                patch("os.open", side_effect=AssertionError("custody")):
            value, material_plan = self.bind()
        generate.assert_not_called()
        plan = material_plan["bootstrap_plan"]
        self.assertEqual(verified_plan(plan, expected_digest=plan["digest"], driver_image_id=sibling.DRIVER), plan)
        self.assertEqual({n["node_id"] for n in plan["resources"]["nodes"]},
            {sibling.IDENTITY + "-" + r for r in ("cpk", "postgres", "secrets")})
        cpk = next(n for n in plan["resources"]["nodes"] if n["node_id"] == sibling.IDENTITY + "-cpk")
        self.assertEqual(cpk["environment"]["CPK_MCP_PROFILE"], "grandparent-read-only-v1")
        self.assertTrue(cpk["image"].endswith("@" + sibling.CPK))
        self.assertIsNone(plan["website_node_id"])
        self.assertNotIn("commissioning", value)
        self.assertNotIn("website", value["bootstrap_input"]["installation"])
        self.assertNotIn("provider_policy", value)
        self.assertEqual(value["permissions"]["worker"], ["instance:workspace:read"])
        self.assertEqual(value["capabilities"], [])
        self.assertIsNone(value["management"])
        self.assertLessEqual(len(plan["resources"]["volumes"]), 10)
        print("sibling public composition: frozen installer, synthetic trust, three nodes; no generation/runtime")

    def test_foreign_commissioning_or_changed_grants_refuse(self):
        changed = deepcopy(self.plan)
        changed["input"]["workspace_id"] = "foreign-root"
        with self.assertRaises(ValueError):
            sibling.bind_material(self.template, changed, self.raw, self.completion)
        self.template["permissions"]["worker"].append("execution:operate")
        with self.assertRaises(ValueError):
            self.bind()

    def test_public_website_product_and_native_create_spec_bind_only_new_receipt(self):
        # Installer has no website package; import its existing public factory
        # from the selected source, never a copied protocol implementation.
        sys.path.insert(0, "/source/products/website_server/src")
        import control_plane_kit_core as core
        from control_plane_kit_servers_website_server.managed import source_runtime_contract
        artifact = sibling.website_artifact(self.raw, "3" * 32)
        contract = source_runtime_contract(artifact)
        config = core.ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode())
        original = core.ReceiverNodeControlConfigurationCodec().decode_bytes(self.public["artifacts"]["cpk"]["content"].encode())
        self.assertEqual(config.verifiers, original.verifiers)
        self.assertEqual(config.target.node_id.value, sibling.IDENTITY + "-website")
        self.assertEqual(config.declaration.surface.variables, ())
        self.assertEqual(contract.configuration_artifacts, (artifact,))
        _, material = self.bind()
        plan = material["bootstrap_plan"]
        receipt = dict(phase="complete", pending=None, plan_digest=plan["digest"],
            driver_image_id=sibling.DRIVER, engine_id="synthetic-daemon",
            setup_workspace_id=sibling.IDENTITY, labels={"org.openj92.cpk.installation": sibling.IDENTITY},
            resources=dict(networks={plan["resources"]["network"]["name"]: {"id": "a" * 64}},
                containers={sibling.IDENTITY + "-cpk": {"id": "b" * 64}}))
        action = sibling.website_action(plan, dict(status="local-ready", receipt=receipt), artifact)
        self.assertEqual(action["network_id"], "a" * 64)
        self.assertIn("CPK_WEB_UPSTREAM=" + sibling.UPSTREAM, action["create_argv"])
        self.assertEqual(action["create_argv"][-1], sibling.WEBSITE)
        self.assertFalse(action["approved"])
        receipt["plan_digest"] = "foreign-plan"
        with self.assertRaises(ValueError):
            sibling.website_action(plan, dict(status="local-ready", receipt=receipt), artifact)


if __name__ == "__main__":
    unittest.main()
