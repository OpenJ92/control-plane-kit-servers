"""Root public planning and pre-acquisition admission of private installer intent."""
import copy
from dataclasses import replace
import hashlib
import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import ProductDescriptorCodec
from managed_native_material import NativeMaterial
from test_root_bootstrap import DRIVER, installation_input


POLICY_PATH = "/etc/cpk/cpk-server/workspace-authority.json"
ISSUER = "urn:control-plane-kit:static-development"
TOKEN = "synthetic-private-installer-token"


class DynamicRootBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")
        self.health = importlib.import_module("control_plane_kit_servers_cpk_server.managed_health_configuration")
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def inputs(self, *, multiple=False, health=False):
        document = installation_input()
        installation = document["installation"]
        installer = {"issuer": ISSUER, "subject_id": "installer-private" if multiple else
            "local-development-operator", "kind": "operator"}
        target = {"issuer": ISSUER, "subject_id": "grant-target-private", "kind": "operator"}
        policy = {"schema": "cpk-server.workspace-authority.v1", "installation_id": installation["installation_id"],
            "administrators": [installer], "known_identities": [installer, target],
            "capabilities": ["installed-management"]}
        policy_bytes = self.api.canonical(policy)
        administration = {"workspace_creation_idempotency_key": "private-create-key",
            "permission_grants": [{"target": target, "scopes": ["instance:workspace:read"],
                "expected_revision": 0, "idempotency_key": "private-grant-key"}],
            "management_grant": None}
        document["setup"]["administration"] = {"permission_grant_count": 1, "management_grant": False}
        private = {"policy": {"file": "policy-private.json", "sha256": hashlib.sha256(policy_bytes).hexdigest()},
            "installer": installer, "initialization_idempotency_key": "private-initialize-key",
            "administration": administration}
        self.bind_intent(document, policy_bytes, private)
        installation["workspace_grants"] = []
        if multiple:
            installation["control_auth"] = {"kind": "multi-principal",
                "principals_document": "secret://bootstrap/root-a/principals"}
        if health:
            world = NativeMaterial()
            raw = self.api.canonical({"schema": "cpk-server.managed-health.v2",
                "docker": {"socket_path": "/var/run/docker.sock", "request_timeout": 5.0},
                "capability_ids": ["installed-management"],
                "gateway_documents": [world.authored.documents["gateway"].content.decode()],
                "native_product_document": world.document.content.decode()})
            installation["managed_health_configuration"] = ConfigurationArtifact(
                self.health.MANAGED_HEALTH_ARTIFACT_ID, self.health.MANAGED_HEALTH_CONFIGURATION_PATH,
                ConfigurationMediaType.JSON, raw.decode()).descriptor()
        return document, policy_bytes, private

    def bind_intent(self, document, policy_bytes, private):
        private["policy"]["sha256"] = hashlib.sha256(policy_bytes).hexdigest()
        binding = {"policy_sha256": private["policy"]["sha256"], "installer": private["installer"],
            "initialization_idempotency_key": private["initialization_idempotency_key"],
            "setup_sha256": hashlib.sha256(self.api.canonical({"public_setup": document["setup"],
                "administration": private["administration"]})).hexdigest()}
        document["installation"]["workspace_authority"] = {"mode": "dynamic-v1",
            "private_intent_sha256": hashlib.sha256(self.api.canonical(binding)).hexdigest()}

    def private_write(self, path, raw):
        if path.exists():
            path.chmod(0o600)
        path.write_bytes(raw)
        path.chmod(0o400)

    def plan(self, document):
        return self.api.plan_root_bootstrap(document, driver_image_id=DRIVER)

    def test_dynamic_launcher_authoring_uses_real_contracts_and_admissible_private_intent(self):
        from products.cpk_server.tests import live_root_bootstrap as witness
        document = installation_input()
        # Authoring evidence only: historical CPK account coordinates and an
        # inert Secrets reference do not qualify this pair for execution.
        selection = {"images": {"cpk-server": witness.CPK_IMAGE_ACCOUNT.image_reference,
            "secrets-server": "ghcr.io/openj92/control-plane-kit-servers/secrets-server@sha256:" + "a" * 64}}
        with patch.object(witness, "ROOT", self.root):
            policy, private = witness.prepare_dynamic_document(document, selection, DRIVER)
        plan = self.plan(document)
        path, _ = self.material(plan, policy, private)
        runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        _, admitted = runtime._material(plan, path)
        self.assertEqual(admitted.policy_bytes, policy)
        self.assertEqual(len(plan["resources"]["nodes"]), 3)
        self.assertNotIn("website", document["installation"])
        for role in ("cpk", "secrets"):
            node = next(node for node in plan["resources"]["nodes"]
                if node["node_id"] == document["installation"]["installation_id"] + "-" + role)
            self.assertEqual(node["image"], selection["images"][role + "-server"])
            self.assertTrue(node["configuration_files"])
        self.assertEqual(plan["setup_routes"][:2], ["command.workspace-administration.create",
            "command.workspace-permission.grant"])
        self.assertIn("command.managed-runtime-access.grant", plan["setup_routes"])

    def test_dynamic_launcher_unknown_account_baseline_refuses_before_commissioning(self):
        from products.cpk_server.tests import live_root_bootstrap as witness
        selection = {"images": {"cpk-server":
            "ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:" + "b" * 64}}
        with patch.object(witness, "ROOT", self.root):
            with self.assertRaisesRegex(AssertionError, "no reviewed image account baseline"):
                witness.prepare_dynamic_document(installation_input(), selection, DRIVER)
        self.assertFalse((self.root / "commissioning").exists())

    def test_dynamic_launcher_emitted_private_files_are_admitted_together(self):
        from products.cpk_server.tests import live_root_bootstrap as witness
        from products.cpk_server.examples.root_bootstrap_input import example_input
        source = Path(__file__).resolve().parents[3]
        environment = {"CPK_ROOT_ARTIFACT_MODE": "published-digest",
            "CPK_ROOT_CPK_IMAGE": witness.CPK_IMAGE_ACCOUNT.image_reference,
            "CPK_ROOT_SECRETS_IMAGE": "ghcr.io/openj92/control-plane-kit-servers/secrets-server@sha256:" + "a" * 64,
            "CPK_ROOT_SOURCE_REVISION": "a" * 40, "CPK_ROOT_DRIVER_IMAGE_ID": DRIVER}
        old_umask = os.umask(0o077)
        try:
            # Only the separate image-packaging subprocess is outside this
            # writer target; commissioning and all emitted material are real.
            with patch.object(witness, "ROOT", self.root), patch.dict(os.environ, environment), \
                    patch.object(witness, "commissioning_driver_witness"), \
                    patch.object(witness, "example_input", side_effect=lambda **kw: example_input(source, **kw)):
                witness.prepare("root-writer")
        finally:
            os.umask(old_umask)
        document = json.loads((self.root / "input.json").read_bytes())
        plan = self.plan(document)
        index = self.root / "material" / "index.json"
        runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        material, admitted = runtime._material(plan, index)
        self.assertEqual(admitted.policy_bytes, (self.root / "material" / "workspace-authority.json").read_bytes())
        self.assertEqual(json.loads(index.read_bytes())["dynamic_workspace"]["plan_digest"], plan["digest"])
        installation = document["installation"]
        principals = json.loads(material[installation["control_auth"]["principals_document"]])
        self.assertEqual(principals[0]["credential"], material[installation["references"]["control_credential"]])
        for path in (self.root / "material").iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o400)

    def material(self, plan, policy_bytes, private, *, bearer=TOKEN, principal_subject=None):
        files = {}
        installation = plan["input"]["installation"]
        for number, reference in enumerate(plan["required_material"]):
            path = self.root / ("credential-" + str(number))
            value = "synthetic-unused-material"
            if reference == installation["references"]["control_credential"]:
                value = bearer
            if reference == installation.get("control_auth", {}).get("principals_document"):
                value = json.dumps([{"credential": TOKEN,
                    "subject_id": principal_subject or private["installer"]["subject_id"],
                    "kind": "operator", "workspace_grants": {}}])
            self.private_write(path, value.encode())
            files[reference] = path.name
        policy_path = self.root / private["policy"]["file"]
        self.private_write(policy_path, policy_bytes)
        index = {"schema": "cpk.root-bootstrap.material.v2", "files": files,
            "dynamic_workspace": {**private, "plan_digest": plan["digest"]}}
        path = self.root / "index.json"
        self.private_write(path, self.api.canonical(index))
        return path, index

    def refused_before_docker(self, plan, index, reason):
        state = self.root / "state"
        with patch("docker.DockerClient") as client, patch("docker.from_env") as ambient:
            with self.assertRaises(self.api.RootBootstrapError) as caught:
                self.api.apply_root_bootstrap(plan, expected_digest=plan["digest"], driver_image_id=DRIVER,
                    index_path=index, state_directory=state)
        client.assert_not_called()
        ambient.assert_not_called()
        result = self.api.bootstrap_failure(caught.exception)
        self.assertEqual(result["reason"], reason)
        rendered = json.dumps(result) + str(caught.exception) + repr(caught.exception)
        for private_value in (TOKEN, "grant-target-private", "private-grant-key", "private-initialize-key"):
            self.assertNotIn(private_value, rendered)
        self.assertFalse((state / "receipt.json").exists())
        return caught.exception

    def test_dynamic_public_plan_declares_retained_private_delivery_without_private_intent(self):
        document, policy_bytes, private = self.inputs()
        with patch("docker.DockerClient") as client, patch("os.open") as files:
            plan = self.plan(document)
        client.assert_not_called()
        files.assert_not_called()
        cpk = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["cpk_node_id"])
        self.assertEqual(cpk["environment"]["CPK_WORKSPACE_AUTHORITY"], "dynamic-v1")
        self.assertEqual(cpk["environment"]["CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE"], POLICY_PATH)
        self.assertEqual(json.loads(cpk["environment"]["CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON"]), {})
        delivery, = cpk["installer_files"]
        self.assertEqual((delivery["role"], delivery["schema"], delivery["target"], delivery["lifetime"]),
            ("workspace-authority", "cpk-server.workspace-authority.v1", POLICY_PATH, "installation"))
        self.assertTrue(delivery["name"])
        self.assertFalse(any(entry["target"] == POLICY_PATH for entry in
            (*cpk["configuration_files"], *cpk["secret_files"], *cpk["data_volumes"])))
        rendered = self.api.canonical(plan).decode()
        for private_value in (policy_bytes.decode(), private["policy"]["file"], "administrators",
                "known_identities", "grant-target-private", "private-create-key", "private-grant-key"):
            self.assertNotIn(private_value, rendered)
        self.assertEqual(plan["setup_routes"][:2], ["command.workspace-administration.create",
            "command.workspace-permission.grant"])
        self.assertEqual(self.api.verified_plan(plan, plan["digest"], DRIVER), plan)

    def test_dynamic_input_summary_is_closed_and_static_input_retains_legacy_entrance(self):
        legacy = self.plan(installation_input())
        self.assertEqual(legacy["setup_routes"][0], "command.workspace.create")
        self.assertFalse(any(node.get("installer_files") for node in legacy["resources"]["nodes"]))
        document, _, _ = self.inputs()
        self.plan(document)
        cases = []
        for summary in ({"permission_grant_count": True, "management_grant": False},
                {"permission_grant_count": 0, "management_grant": False},
                {"permission_grant_count": 33, "management_grant": False},
                {"permission_grant_count": 1, "management_grant": 0},
                {"permission_grant_count": 1, "management_grant": False, "target": "private"}):
            candidate = copy.deepcopy(document)
            candidate["setup"]["administration"] = summary
            cases.append(candidate)
        candidate = copy.deepcopy(document)
        candidate["installation"]["workspace_grants"] = installation_input()["installation"]["workspace_grants"]
        cases.append(candidate)
        for candidate in cases:
            with self.subTest(candidate=candidate["setup"]["administration"]):
                with self.assertRaises(self.api.RootBootstrapError):
                    self.plan(candidate)

    def test_health_v2_is_admitted_only_with_explicit_dynamic_installer_delivery(self):
        document, _, _ = self.inputs(health=True)
        raw = document["installation"]["managed_health_configuration"]["content"].encode()
        with self.assertRaises(ValueError):
            self.health.managed_health_configuration_artifact(raw)
        plan = self.plan(document)
        cpk = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["cpk_node_id"])
        self.assertEqual(cpk["environment"]["CPK_MANAGED_HEALTH"], "docker-unix-v2")
        artifact = next(entry["artifact"] for entry in cpk["configuration_files"]
            if entry["target"] == self.health.MANAGED_HEALTH_CONFIGURATION_PATH)
        self.assertEqual(artifact["content"].encode(), raw)
        static = installation_input()
        static["installation"]["managed_health_configuration"] = artifact
        with self.assertRaises(self.api.RootBootstrapError):
            self.plan(static)

    def test_private_policy_and_same_count_intent_drift_refuse_before_acquisition(self):
        document, policy_bytes, private = self.inputs()
        plan = self.plan(document)
        path, original = self.material(plan, policy_bytes, private)
        changes = []
        for field, value in (("target", {**private["administration"]["permission_grants"][0]["target"],
                "subject_id": "another-private-target"}), ("scopes", ["instance:workspace:edit"]),
                ("idempotency_key", "another-private-key")):
            candidate = copy.deepcopy(original)
            candidate["dynamic_workspace"]["administration"]["permission_grants"][0][field] = value
            changes.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["dynamic_workspace"]["administration"]["permission_grants"] = []
        changes.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["dynamic_workspace"]["plan_digest"] = "0" * 64
        changes.append(candidate)
        for candidate in changes:
            self.private_write(path, self.api.canonical(candidate))
            self.refused_before_docker(plan, path, "material-refused")
        self.private_write(path, self.api.canonical(original))
        self.private_write(self.root / private["policy"]["file"], policy_bytes + b"\n")
        self.refused_before_docker(plan, path, "material-refused")

    def test_private_summary_and_health_catalogue_must_match_even_with_valid_commitment(self):
        for summary in ({"permission_grant_count": 2, "management_grant": False},
                {"permission_grant_count": 1, "management_grant": True}):
            document, policy_bytes, private = self.inputs()
            document["setup"]["administration"] = summary
            self.bind_intent(document, policy_bytes, private)
            plan = self.plan(document)
            path, _ = self.material(plan, policy_bytes, private)
            self.refused_before_docker(plan, path, "material-refused")
        document, policy_bytes, private = self.inputs(health=True)
        policy = json.loads(policy_bytes)
        policy["capabilities"] = ["different-installed-management"]
        policy_bytes = self.api.canonical(policy)
        self.bind_intent(document, policy_bytes, private)
        plan = self.plan(document)
        path, _ = self.material(plan, policy_bytes, private)
        self.refused_before_docker(plan, path, "material-refused")

    def test_actual_setup_bearer_mapping_is_checked_before_acquisition(self):
        for multiple in (False, True):
            with self.subTest(multiple=multiple):
                document, policy_bytes, private = self.inputs(multiple=multiple)
                plan = self.plan(document)
                path, _ = self.material(plan, policy_bytes, private)
                with patch("docker.DockerClient", side_effect=RuntimeError("synthetic provider unavailable")) as client:
                    with self.assertRaises(self.api.RootBootstrapError):
                        self.api.apply_root_bootstrap(plan, expected_digest=plan["digest"], driver_image_id=DRIVER,
                            index_path=path, state_directory=self.root / "state")
                client.assert_called_once()
                if multiple:
                    path, _ = self.material(plan, policy_bytes, private, bearer="unverified-private-token")
                    self.refused_before_docker(plan, path, "material-refused")
                    path, _ = self.material(plan, policy_bytes, private, principal_subject="grant-target-private")
                    self.refused_before_docker(plan, path, "material-refused")
                else:
                    policy = json.loads(policy_bytes)
                    private["installer"] = policy["known_identities"][1]
                    policy["administrators"] = [private["installer"]]
                    policy_bytes = self.api.canonical(policy)
                    self.bind_intent(document, policy_bytes, private)
                    plan = self.plan(document)
                    path, _ = self.material(plan, policy_bytes, private)
                    self.refused_before_docker(plan, path, "material-refused")

    def test_existing_acquisition_receipt_wins_before_private_material_read(self):
        document, _, _ = self.inputs()
        plan = self.plan(document)
        state = self.root / "state"
        state.mkdir(mode=0o700)
        receipt = state / "receipt.json"
        receipt.write_text("existing private acquisition evidence")
        before = receipt.read_bytes()
        with patch("docker.DockerClient") as client, patch("os.open") as files:
            with self.assertRaises(self.api.RootBootstrapError) as caught:
                self.api.apply_root_bootstrap(plan, expected_digest=plan["digest"], driver_image_id=DRIVER,
                    index_path=self.root / "missing-index", state_directory=state)
        client.assert_not_called()
        files.assert_not_called()
        self.assertEqual(self.api.bootstrap_failure(caught.exception)["reason"], "prior-acquisition")
        self.assertEqual(receipt.read_bytes(), before)

    def test_dynamic_reserved_environment_and_policy_path_cannot_be_supplied_by_product(self):
        codec = ProductDescriptorCodec()
        for conflict in ("environment", "file", "parent-file"):
            with self.subTest(conflict=conflict):
                document, _, _ = self.inputs()
                selected = codec.decode_document(document["installation"]["products"]["cpk"])
                contract = selected.product.runtime_contract
                if conflict == "environment":
                    contract = replace(contract, public_environment=(*contract.public_environment,
                        PublicStaticEnvironmentBinding("CPK_WORKSPACE_AUTHORITY", "disabled")))
                else:
                    artifact = ConfigurationArtifact("unrelated", POLICY_PATH if conflict == "file" else
                        "/etc/cpk/cpk-server", ConfigurationMediaType.JSON, "{}")
                    contract = replace(contract, configuration_artifacts=(*contract.configuration_artifacts, artifact))
                document["installation"]["products"]["cpk"] = json.loads(codec.encode_document(
                    replace(selected.product, runtime_contract=contract)).content)
                with self.assertRaises(self.api.RootBootstrapError):
                    self.plan(document)

    def test_valid_health_and_management_intent_is_admitted_without_registration_effect(self):
        document, policy_bytes, private = self.inputs(health=True)
        document["setup"]["administration"]["management_grant"] = True
        private["administration"]["management_grant"] = {
            "runtime_id": document["installation"]["installation_id"] + "-docker",
            "authority_ref": document["installation"]["runtime_authority"],
            "capability_id": "installed-management", "expected_revision": 0,
            "idempotency_key": "private-management-key", "registration_from": "command.runtime-authority.register"}
        self.bind_intent(document, policy_bytes, private)
        plan = self.plan(document)
        routes = plan["setup_routes"]
        self.assertEqual(routes[routes.index("command.runtime-authority.register") + 1],
            "command.managed-runtime-access.grant")
        path, _ = self.material(plan, policy_bytes, private)
        runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        with patch("docker.DockerClient") as client:
            _, admitted = runtime._material(plan, path)
        client.assert_not_called()
        self.assertEqual(admitted.policy_bytes, policy_bytes)
        private["administration"]["management_grant"]["registration_id"] = "fabricated-registration"
        self.bind_intent(document, policy_bytes, private)
        plan = self.plan(document)
        path, _ = self.material(plan, policy_bytes, private)
        self.refused_before_docker(plan, path, "material-refused")

    def test_policy_read_retains_admitted_bytes_and_hides_private_context(self):
        document, policy_bytes, private = self.inputs()
        plan = self.plan(document)
        path, _ = self.material(plan, policy_bytes, private)
        runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        with patch("docker.DockerClient") as client:
            credentials, admitted = runtime._material(plan, path)
        client.assert_not_called()
        self.private_write(self.root / private["policy"]["file"], b"changed after admission")
        self.assertEqual(admitted.policy_bytes, policy_bytes)
        self.assertEqual(set(credentials), set(plan["required_material"]))
        for value in ("grant-target-private", "private-initialize-key", "private-grant-key"):
            self.assertNotIn(value, repr(admitted))
        self.refused_before_docker(plan, path, "material-refused")

    def test_private_schema_unknown_fields_and_unsafe_or_public_policy_file_are_refused(self):
        document, policy_bytes, private = self.inputs()
        plan = self.plan(document)
        path, original = self.material(plan, policy_bytes, private)
        changes = []
        for field, value in (("schema", "cpk.root-bootstrap.material.v1"), ("extra", True)):
            candidate = copy.deepcopy(original)
            candidate[field] = value
            changes.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["dynamic_workspace"]["policy"]["file"] = "../outside-policy"
        changes.append(candidate)
        for candidate in changes:
            self.private_write(path, self.api.canonical(candidate))
            self.refused_before_docker(plan, path, "material-refused")
        self.private_write(path, self.api.canonical(original))
        (self.root / private["policy"]["file"]).chmod(0o644)
        self.refused_before_docker(plan, path, "material-refused")

    def test_malformed_owner_keys_refuse_without_private_exception_context(self):
        from control_plane_kit_operations.workflows import InvalidOperationCommand
        for site in ("initialization", "workspace-create", "permission-grant", "management-grant"):
            with self.subTest(site=site):
                document, policy_bytes, private = self.inputs(health=True)
                administration = private["administration"]
                canary = "private-invalid-key-canary-" * 10
                if site == "initialization":
                    private["initialization_idempotency_key"] = canary
                elif site == "workspace-create":
                    administration["workspace_creation_idempotency_key"] = canary
                elif site == "permission-grant":
                    administration["permission_grants"][0]["idempotency_key"] = canary
                else:
                    document["setup"]["administration"]["management_grant"] = True
                    administration["management_grant"] = {
                        "runtime_id": document["installation"]["installation_id"] + "-docker",
                        "authority_ref": document["installation"]["runtime_authority"],
                        "capability_id": "installed-management", "expected_revision": 0,
                        "idempotency_key": canary, "registration_from": "command.runtime-authority.register"}
                # Rebind correctly: this must exercise owner validation, not hash drift.
                self.bind_intent(document, policy_bytes, private)
                plan = self.plan(document)
                path, _ = self.material(plan, policy_bytes, private)
                error = self.refused_before_docker(plan, path, "material-refused")
                while error is not None:
                    self.assertNotIsInstance(error, InvalidOperationCommand)
                    self.assertIsInstance(error, self.api.RootBootstrapError)
                    self.assertNotIn("private-invalid-key-canary", str(error) + repr(error))
                    self.assertIsNone(error.__cause__)
                    error = error.__context__
