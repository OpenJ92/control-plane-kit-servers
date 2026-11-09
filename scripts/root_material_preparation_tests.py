"""Offline installer evidence, public-only receiving trust, no service effects."""
from contextlib import redirect_stdout
import copy
from dataclasses import replace
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from control_plane_kit_core.configuration import ConfigurationArtifact
from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_servers_cpk_server import root_material_preparation as api
from control_plane_kit_servers_cpk_server import root_commissioning as commissioning
from control_plane_kit_servers_cpk_server.bootstrap import canonical
from control_plane_kit_servers_cpk_server.bootstrap_runtime import _material, private_read
from control_plane_kit_servers_cpk_server.server import CpkServerBootstrapConfiguration, _credential_verifier
from control_plane_kit_servers_cpk_server.workspace_authority_configuration import decode_workspace_authority_configuration
from control_plane_kit_servers_cpk_server.control_configuration import cpk_source_runtime_contract, CpkSourceVariant
from control_plane_kit_servers_secrets_server.configuration import secrets_source_runtime_contract
from test_root_bootstrap import installation_input, DRIVER


class RootMaterialPreparationTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.state = self.root / "preparation" / "material"
        self.state.parent.mkdir(mode=0o700)
        document = installation_input()
        installation = document["installation"]
        intent = dict(schema="cpk.root-commissioning.intent.v1", installation_id=installation["installation_id"],
            workspace_id=installation["workspace_id"], profile="operator-offline-read-trust",
            custody=dict(host_directory=str(self.root / "public-only"), uid=os.geteuid(), gid=os.getegid()))
        plan = commissioning.plan_root_commissioning(intent, preparer_image_id=DRIVER)
        # Real owner rendering, using synthetic test keys in memory only. The
        # new preparer never receives or opens them; no PEM files even exist.
        purposes = tuple(commissioning.PURPOSE_FILES)
        public = commissioning._render(plan, dict(cpk="c" * 32, secrets="d" * 32),
            {purpose:Ed25519PrivateKey.generate() for purpose in purposes},
            {purpose:"key-" + str(index) for index,purpose in enumerate(purposes)})
        public_raw = commissioning._canonical(public)
        complete = commissioning._completion(plan, public["receiver_ids"], public_raw)
        codec = ProductDescriptorCodec()
        for role in ("cpk", "secrets"):
            artifact = ConfigurationArtifact.from_descriptor(public["artifacts"][role])
            contract = (cpk_source_runtime_contract(CpkSourceVariant.DOCKER_CLOUDFLARE, artifact)
                if role == "cpk" else secrets_source_runtime_contract(artifact))
            original = codec.decode_document(installation["products"][role])
            installation["products"][role] = json.loads(codec.encode_document(replace(original.product,
                runtime_contract=contract)).content)
        installation["workspace_grants"] = []
        installation["control_auth"] = dict(kind="multi-principal", principals_document="secret://bootstrap/root-a/principals")
        identities = {role:dict(issuer="urn:control-plane-kit:static-development", subject_id="test-" + role,
            kind="worker" if role == "worker" else "operator") for role in ("human", "setup", "worker")}
        self.document = dict(schema="cpk.root-material.intent.v1", bootstrap_input=document,
            principals=identities, permissions=dict(human=["instance:workspace:read"],
                setup=["instance:workspace:read", "instance:workspace:edit", "runtime-authority:register"],
                worker=["execution:operate", "runtime-authority:use"]), capabilities=["test-managed"], management=None,
            provider_grants=[dict(action="secret.resolve", workspace_id=installation["workspace_id"],
                intents=["postgres.password", "application.control-token"])],
            custody=dict(host_directory=str(self.state), uid=os.geteuid(), gid=os.getegid()),
            commissioning=dict(plan=plan, intent_digest=plan["digest"], public_utf8=public_raw.decode(),
                public_sha256=sha256(public_raw).hexdigest(), completion=complete))

    def plan(self, document=None):
        return api.plan_root_material_preparation(self.document if document is None else document, driver_image_id=DRIVER)

    def prepare(self, plan=None):
        plan = self.plan() if plan is None else plan
        return api.prepare_root_material(plan, expected_digest=plan["digest"], driver_image_id=DRIVER, state_directory=self.state)

    def test_plan_is_pure_and_uses_public_only_commissioning_with_real_bootstrap_digest(self):
        with patch.object(api.secrets, "token_urlsafe", side_effect=AssertionError("plan generated token")), \
                patch.object(api.os, "urandom", side_effect=AssertionError("plan generated key")), \
                patch.object(commissioning, "_reuse", side_effect=AssertionError("private commissioning accessed")), \
                patch.object(api, "_write", side_effect=AssertionError("plan wrote file")):
            plan = self.plan()
            self.assertEqual(plan, self.plan())
        self.assertFalse(self.state.exists())
        self.assertNotEqual(plan["digest"], plan["bootstrap_plan"]["digest"])
        self.assertNotIn("PRIVATE KEY", canonical(plan).decode())
        self.assertEqual(list(self.state.parent.iterdir()), [])
        other_driver = "sha256:" + "b" * 64
        other = api.plan_root_material_preparation(self.document, driver_image_id=other_driver)
        self.assertEqual(other["bootstrap_plan"]["driver_image_id"], other_driver)
        self.assertEqual(other["input"]["commissioning"]["plan"]["preparer_image_id"], DRIVER)

    def test_prepare_passes_existing_material_owner_and_three_real_auth_identities(self):
        plan = self.plan()
        with patch.object(commissioning, "_reuse", side_effect=AssertionError("private commissioning accessed")):
            receipt = self.prepare(plan)
        self.assertEqual(receipt["bootstrap_plan_digest"], plan["bootstrap_plan"]["digest"])
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o700)
        index = json.loads(private_read(self.state / "index.json"))
        self.assertEqual(index["dynamic_workspace"]["plan_digest"], plan["bootstrap_plan"]["digest"])
        values, admitted = _material(plan["bootstrap_plan"], self.state / "index.json")
        authority = decode_workspace_authority_configuration(private_read(self.state / "workspace-authority.json"))
        root = plan["bootstrap_plan"]
        node = next(node for node in root["resources"]["nodes"] if node["node_id"] == root["cpk_node_id"])
        principals = values[root["input"]["installation"]["control_auth"]["principals_document"]]
        config = CpkServerBootstrapConfiguration._from_environment({**node["environment"],
            "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON":principals}, workspace_authority=authority)
        verifier = _credential_verifier(config)
        tokens = []
        for role in ("human", "setup", "worker"):
            token = private_read(self.state / (role + ".bearer"))
            tokens.append(token)
            expected = self.document["principals"][role]
            identity = PrincipalIdentity(expected["issuer"], expected["subject_id"], PrincipalKind(expected["kind"]))
            self.assertEqual(verifier.authenticate(token).identity, identity)
            self.assertEqual(identity in authority.administration_policy.administrators, role == "setup")
        self.assertEqual(len(set(tokens)), 3)
        self.assertEqual(admitted.installer.identity, authority.administration_policy.administrators[0])
        rendered = canonical(receipt)
        self.assertTrue(all(token not in rendered for token in tokens))
        for path in self.state.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600 if path.name in {"intent.json", "complete.json"} else 0o400)

    def test_crossed_or_reserialized_public_receipts_refuse_without_allocation(self):
        variants = []
        for change in (dict(public_utf8=self.document["commissioning"]["public_utf8"] + "\n"),
                dict(intent_digest="f" * 64), dict(public_sha256="e" * 64)):
            altered = copy.deepcopy(self.document)
            altered["commissioning"].update(change)
            variants.append(altered)
        altered = copy.deepcopy(self.document)
        altered["commissioning"]["completion"]["receiver_ids"]["cpk"] = "f" * 32
        variants.append(altered)
        for document in variants:
            with self.subTest(variant=variants.index(document)), self.assertRaises(api.RootBootstrapError):
                self.plan(document)
        self.assertFalse(self.state.exists())

    def test_image_driver_digest_or_projection_drift_refuses_before_generation(self):
        plan = self.plan()
        changed = copy.deepcopy(plan)
        changed["bootstrap_plan"]["digest"] = plan["digest"]
        image = copy.deepcopy(plan)
        image["input"]["bootstrap_input"]["installation"]["products"]["cpk"]["product"]["image"]["digest"] = "sha256:" + "f" * 64
        for candidate, driver in ((changed, DRIVER), (image, DRIVER), (plan, "sha256:" + "b" * 64)):
            with patch.object(api.secrets, "token_urlsafe", side_effect=AssertionError("drift generated token")), \
                    self.assertRaises(api.RootBootstrapError):
                api.prepare_root_material(candidate, expected_digest=plan["digest"], driver_image_id=driver, state_directory=self.state)
        self.assertFalse(self.state.exists())

    def test_partial_failure_holds_and_never_mints_replacement_credentials(self):
        actual_write = api._write
        def fail(directory, name, raw, mode=0o400):
            if name == "custody.key":
                raise OSError("test injected write failure")
            return actual_write(directory, name, raw, mode)
        with patch.object(api, "_write", side_effect=fail), self.assertRaises(api.RootBootstrapHold):
            self.prepare()
        self.assertTrue((self.state / "intent.json").exists())
        self.assertFalse((self.state / "complete.json").exists())
        with patch.object(api.secrets, "token_urlsafe", side_effect=AssertionError("partial replay minted token")), \
                self.assertRaises(api.RootBootstrapHold):
            self.prepare()

    def test_completed_destination_is_not_reused_or_private_credentials_read(self):
        self.prepare()
        with patch.object(api.secrets, "token_urlsafe", side_effect=AssertionError("reuse minted token")), \
                patch("control_plane_kit_servers_cpk_server.bootstrap_runtime.private_read",
                    side_effect=AssertionError("reuse read credential")), self.assertRaises(api.RootBootstrapHold):
            self.prepare()

    def test_cli_public_plan_and_completion_never_print_generated_material(self):
        snapshot = self.document["commissioning"]
        manifest = {key:value for key,value in self.document.items() if key != "commissioning"}
        for name, raw in (("input", canonical(manifest)), ("commission-plan", canonical(snapshot["plan"])),
                ("public", snapshot["public_utf8"].encode()), ("complete", canonical(snapshot["completion"]))):
            (self.root / (name + ".json")).write_bytes(raw)
        stdout = io.StringIO()
        args = ["plan", "--driver", DRIVER, "--input", str(self.root / "input.json"),
            "--commission-plan", str(self.root / "commission-plan.json"), "--commission-public", str(self.root / "public.json"),
            "--commission-complete", str(self.root / "complete.json"), "--public-sha256", snapshot["public_sha256"],
            "--commissioning-digest", snapshot["intent_digest"]]
        with redirect_stdout(stdout):
            self.assertEqual(api.main(args), 0)
        plan = json.loads(stdout.getvalue())
        self.assertFalse(self.state.exists())
        (self.root / "plan.json").write_bytes(canonical(plan))
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(api.main(["prepare", "--plan", str(self.root / "plan.json"), "--digest", plan["digest"],
                "--driver", DRIVER, "--state", str(self.state)]), 0)
        output = stdout.getvalue().encode()
        for name in ("human.bearer", "setup.bearer", "worker.bearer", "postgres.password", "provider.token", "custody.key"):
            self.assertFalse(private_read(self.state / name) in output, "private material reached public completion")
