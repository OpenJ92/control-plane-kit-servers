"""Optional fixed policy producer evidence, no provider or service effects."""
import copy
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from control_plane_kit_core.configuration import ConfigurationArtifact
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_secrets import provider_policy
from control_plane_kit_secrets.auth import ProviderAuthorizer
from control_plane_kit_secrets.bootstrap import load_provider_credentials
import root_material_preparation_tests as preparation_tests
from control_plane_kit_servers_cpk_server import root_material_preparation as api, root_commissioning as commissioning
from control_plane_kit_servers_cpk_server.bootstrap import canonical
from control_plane_kit_servers_cpk_server.bootstrap_runtime import private_read
from control_plane_kit_servers_cpk_server.control_configuration import cpk_source_runtime_contract, CpkSourceVariant
from control_plane_kit_servers_secrets_server.configuration import secrets_source_runtime_contract
from test_root_bootstrap import DRIVER


INTENTS = ["postgres.password", "application.control-token", "secrets.custody-root-key",
    "secrets.provider-credentials-document", "cloudflare.api-token", "cloudflare.tunnel-token",
    "gateway.probe-signing-key", "workload.node-health-read-signing-key",
    "gateway.node-health-read-transit-signing-key", "workload.http-verification-sample-signing-key",
    "gateway.http-verification-sample-transit-signing-key"]


class ProviderPreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = preparation_tests.RootMaterialPreparationTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def document(self):
        value = copy.deepcopy(self.fixture.document)
        root = value["bootstrap_input"]["installation"]["workspace_id"]
        value["provider_policy"] = dict(child_workspace_id="child-a",
            cpk_grants=[dict(action="secret.resolve", workspace_id=root,
                intents=["postgres.password", "application.control-token", "cloudflare.tunnel-token"]),
                dict(action="secret.write", workspace_id="child-a", intents=INTENTS),
                dict(action="secret.resolve", workspace_id="child-a", intents=INTENTS),
                dict(action="secret.metadata", workspace_id="child-a", intents=[])],
            external_provisioner_subject="root-a-external-provisioner",
            external_provisioner_grants=[dict(action="secret.write", workspace_id=root,
                intents=["cloudflare.tunnel-token"])])
        return value

    def test_exact_provider_owner_export_is_selected(self):
        self.assertTrue(Path(provider_policy.__file__).is_relative_to("/reviewed-http-sample/secrets/src"))
        self.assertEqual(os.environ["CPK_SOURCE_SECRETS_REVISION"], "57e4fc61d6931ef078550f98154a585bda61987b")

    def test_optional_plan_is_pure_and_outputs_only_one_extra_protected_credential(self):
        value = self.document()
        with patch.object(api.secrets, "token_urlsafe", side_effect=AssertionError("planning token")), \
                patch.object(api.os, "urandom", side_effect=AssertionError("planning key")):
            plan = self.fixture.plan(value)
        legacy = self.fixture.plan()
        self.assertEqual(plan["outputs"], legacy["outputs"] + ["external-provisioner.token"])
        self.assertEqual(plan["files"], legacy["files"])
        self.assertFalse(self.fixture.state.exists())

    def test_real_credentials_have_exact_split_seed_and_no_control_bearer_alias(self):
        value = self.document()
        plan = self.fixture.plan(value)
        receipt = self.fixture.prepare(plan)
        state = self.fixture.state
        credentials = load_provider_credentials({"CPK_SECRETS_CREDENTIALS_FILE": str(state / "provider-credentials.json")})
        self.assertEqual(len(credentials), 2)
        self.assertEqual([credential.subject for credential in credentials], ["root-root-a", "root-a-external-provisioner"])
        self.assertTrue(all(credential.capabilities == () for credential in credentials))
        seed = provider_policy._canonical_seed(credentials)
        self.assertEqual(len(seed), 27)
        self.assertEqual({(grant.workspace_id, grant.action, grant.intent) for grant in seed
            if grant.subject == "root-a-external-provisioner"}, {("root-workspace", "secret.write", "cloudflare.tunnel-token")})
        self.assertEqual([(grant.workspace_id, grant.intent) for grant in seed if grant.action == "secret.metadata"], [("child-a", None)])
        tokens = [private_read(state / name) for name in ("human.bearer", "setup.bearer", "worker.bearer", "provider.token", "external-provisioner.token")]
        self.assertEqual(len(set(tokens)), 5)
        authorizer = ProviderAuthorizer(credentials)
        self.assertIs(authorizer.authenticate("Bearer " + tokens[-1].decode()), credentials[1])
        index = json.loads(private_read(state / "index.json"))
        self.assertNotIn("external-provisioner.token", index["files"].values())
        self.assertFalse(tokens[-1].decode() in private_read(state / "principals.json").decode(), "external credential reached login document")
        for node in plan["bootstrap_plan"]["resources"]["nodes"]:
            self.assertNotIn("external-provisioner.token", canonical(node).decode())
        self.assertTrue(all(token not in canonical(receipt) for token in tokens))
        self.assertEqual(stat.S_IMODE((state / "external-provisioner.token").stat().st_mode), 0o400)

    def test_wider_or_ambiguous_optional_policy_refuses_before_allocation(self):
        variants = []
        for field, value in (("workspace_id", "third-workspace"), ("action", "secret.generate-delegation-key"),
                ("intents", ["oci.pull-credential"]), ("intents", ["*"])):
            document = self.document()
            document["provider_policy"]["cpk_grants"][1][field] = value
            variants.append(document)
        for replacement in ("root-workspace", "*"):
            document = self.document()
            document["provider_policy"]["child_workspace_id"] = replacement
            variants.append(document)
        for subject in ("root-root-a", "*"):
            document = self.document()
            document["provider_policy"]["external_provisioner_subject"] = subject
            variants.append(document)
        for workspace in ("root-workspace", "third-workspace"):
            document = self.document()
            document["provider_policy"]["cpk_grants"][-1]["workspace_id"] = workspace
            variants.append(document)
        document = self.document()
        document["provider_policy"]["external_provisioner_grants"][0]["action"] = "secret.resolve"
        variants.append(document)
        document = self.document()
        document["provider_grants"][0]["intents"] = ["oci.pull-credential"]
        document["provider_policy"]["cpk_grants"][0]["intents"].append("oci.pull-credential")
        variants.append(document)
        document = self.document()
        document["provider_policy"]["cpk_grants"].append(copy.deepcopy(document["provider_policy"]["cpk_grants"][1]))
        variants.append(document)
        document = self.document()
        document["provider_policy"]["capabilities"] = ["secrets.policy-admin"]
        variants.append(document)
        for index, document in enumerate(variants):
            with self.subTest(variant=index), patch.object(api.secrets, "token_urlsafe") as entropy, \
                    self.assertRaises(api.RootBootstrapError):
                self.fixture.plan(document)
            entropy.assert_not_called()
            self.assertFalse(self.fixture.state.exists())

    def test_fixed_legacy_plan_digest_and_output_inventory_remain_unchanged(self):
        value = copy.deepcopy(self.fixture.document)
        intent = copy.deepcopy(value["commissioning"]["plan"]["input"])
        intent["custody"]["host_directory"] = "/fixture/public-only"
        plan = commissioning.plan_root_commissioning(intent, preparer_image_id=DRIVER)
        purposes = tuple(commissioning.PURPOSE_FILES)
        public = commissioning._render(plan, dict(cpk="c" * 32, secrets="d" * 32),
            {purpose:Ed25519PrivateKey.from_private_bytes(bytes([index+1]) * 32) for index,purpose in enumerate(purposes)},
            {purpose:"fixed-" + str(index) for index,purpose in enumerate(purposes)})
        raw = commissioning._canonical(public)
        value["commissioning"] = dict(plan=plan, intent_digest=plan["digest"], public_utf8=raw.decode(),
            public_sha256=sha256(raw).hexdigest(), completion=commissioning._completion(plan, public["receiver_ids"], raw))
        codec = ProductDescriptorCodec()
        for role in ("cpk", "secrets"):
            artifact = ConfigurationArtifact.from_descriptor(public["artifacts"][role])
            contract = (cpk_source_runtime_contract(CpkSourceVariant.DOCKER_CLOUDFLARE, artifact)
                if role == "cpk" else secrets_source_runtime_contract(artifact))
            original = codec.decode_document(value["bootstrap_input"]["installation"]["products"][role])
            value["bootstrap_input"]["installation"]["products"][role] = json.loads(codec.encode_document(
                replace(original.product, runtime_contract=contract)).content)
        value["custody"]["host_directory"] = "/fixture/preparation/material"
        result = self.fixture.plan(value)
        self.assertEqual(result["digest"], "3aa071a54b00b6d0c99c382914e4cb08affda2c80bfa37cad57dd914b23ed18b")
        self.assertEqual(result["outputs"], ["setup.bearer", "postgres.password", "custody.key", "provider.token",
            "provider-credentials.json", "principals.json", "human.bearer", "worker.bearer",
            "workspace-authority.json", "index.json", "bootstrap-input.json", "bootstrap-plan.json"])
        self.assertNotIn("external-provisioner.token", result["outputs"])


if __name__ == "__main__":
    unittest.main()
