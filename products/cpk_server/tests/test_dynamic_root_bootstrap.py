"""Root public planning and pre-acquisition admission of private installer intent."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
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

    def test_actual_setup_bearer_mapping_is_checked_before_incomplete_path_refusal(self):
        for multiple in (False, True):
            with self.subTest(multiple=multiple):
                document, policy_bytes, private = self.inputs(multiple=multiple)
                plan = self.plan(document)
                path, _ = self.material(plan, policy_bytes, private)
                self.refused_before_docker(plan, path, "dynamic-bootstrap-incomplete")
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
