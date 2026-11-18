"""Trusted process values compose existing owners after the installation receipt."""
from dataclasses import replace
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_core.configuration import (
    ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType,
)
from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
from control_plane_kit_operations.workspace_permissions import WorkspacePermissionReadService
from managed_native_material import NativeMaterial
from test_secret_provider_bootstrap import _provider_environment


class WorkspaceProcessConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.server = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        self.health_api = importlib.import_module("control_plane_kit_servers_cpk_server.managed_health_configuration")
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.policy_path = self.root / "workspace-policy.json"
        self.health_path = self.root / "managed-health.json"
        self.administrator = PrincipalIdentity("issuer-a", "administrator-a", PrincipalKind.OPERATOR)
        self.policy_document = {"schema": "cpk-server.workspace-authority.v1", "installation_id": "installation-a",
            "administrators": [self.administrator.descriptor()],
            "known_identities": [self.administrator.descriptor()], "capabilities": ["installed-management-a"]}
        self.write(self.policy_path, self.policy_document)
        self.world = NativeMaterial()
        self.health_document = {"schema": "cpk-server.managed-health.v2",
            "docker": {"socket_path": "/var/run/process-never-opened.sock", "request_timeout": 5.0},
            "capability_ids": ["installed-management-a"],
            "gateway_documents": [self.world.authored.documents["gateway"].content.decode()],
            "native_product_document": self.world.document.content.decode()}
        self.write(self.health_path, self.health_document)

    def write(self, path, document):
        path.write_text(json.dumps(document), encoding="utf-8")

    def environment(self, *, health=False):
        result = {**_provider_environment(self.root / "unread-provider.token"),
            "CPK_WORKSPACE_AUTHORITY": "dynamic-v1",
            "CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE": str(self.policy_path)}
        if health:
            result.update(CPK_MANAGED_HEALTH="docker-unix-v2",
                CPK_MANAGED_HEALTH_CONFIGURATION_FILE=str(self.health_path))
        return result

    def configuration(self, *, health=False):
        return self.server.CpkServerBootstrapConfiguration.from_environment(self.environment(health=health))

    def test_workspace_policy_uses_existing_full_identity_owners_without_health_or_io(self):
        with patch("docker.DockerClient") as constructor, patch("docker.from_env") as ambient, \
                patch.object(self.server.psycopg, "connect") as connect:
            config = self.configuration()
        self.assertIsNotNone(config.workspace_authority, "process input does not construct dynamic workspace policy")
        policy = config.workspace_authority.administration_policy
        self.assertEqual(policy.installation_id, "installation-a")
        self.assertEqual(policy.administrators, (self.administrator,))
        self.assertEqual(policy.known_identities, (self.administrator,))
        self.assertEqual(tuple(value.capability_id for value in config.workspace_authority.capability_policy.capabilities),
            ("installed-management-a",))
        self.assertIsNone(config.managed_health_process)
        constructor.assert_not_called()
        ambient.assert_not_called()
        connect.assert_not_called()

    def test_real_single_and_multi_verifiers_accept_empty_grants_only_with_valid_dynamic_policy(self):
        from control_plane_kit_servers_cpk_server.authentication import CredentialAuthenticationError
        issuer = "urn:control-plane-kit:static-development"
        for multiple in (False, True):
            with self.subTest(multiple=multiple):
                identity = PrincipalIdentity(issuer,
                    "installer-a" if multiple else "local-development-operator", PrincipalKind.OPERATOR)
                policy = {**self.policy_document, "administrators": [identity.descriptor()],
                    "known_identities": [identity.descriptor()]}
                self.write(self.policy_path, policy)
                environment = {**self.environment(), "CPK_CONTROL_AUTH_VERIFIER": "static-development"}
                principal_document = {"credential": "synthetic-process-token", "subject_id": identity.subject_id,
                    "kind": identity.kind.value, "workspace_grants": {}}
                if multiple:
                    environment["CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"] = json.dumps([principal_document])
                else:
                    environment.update(CPK_CONTROL_AUTH_STATIC_CREDENTIAL="synthetic-process-token",
                        CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON="{}")
                config = self.server.CpkServerBootstrapConfiguration.from_environment(environment)
                self.assertIsNotNone(config.workspace_authority)
                verifier = self.server._credential_verifier(config)
                principal = verifier.authenticate(b"synthetic-process-token")
                self.assertEqual(principal.identity, identity)
                self.assertEqual(principal.workspace_grants, ())
                self.assertEqual(config.workspace_authority.administration_policy.administrators, (identity,))
                self.assertIsNone(self.server._configured_principal_authorizer(config))
                with self.assertRaises(CredentialAuthenticationError):
                    verifier.authenticate(b"incorrect-process-token")
                static = {name: value for name, value in environment.items()
                    if not name.startswith("CPK_WORKSPACE_AUTHORITY")}
                with self.assertRaises(self.server.BootstrapConfigurationError):
                    self.server.CpkServerBootstrapConfiguration.from_environment(static)
                absent = dict(environment)
                if multiple:
                    absent["CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"] = json.dumps([
                        {name: value for name, value in principal_document.items() if name != "workspace_grants"}])
                else:
                    absent.pop("CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON")
                with self.assertRaises(self.server.BootstrapConfigurationError):
                    self.server.CpkServerBootstrapConfiguration.from_environment(absent)
                self.write(self.policy_path, {**policy, "schema": "invalid"})
                with self.assertRaises(self.server.BootstrapConfigurationError):
                    self.server.CpkServerBootstrapConfiguration.from_environment(environment)
                self.policy_path.unlink()
                with self.assertRaises(self.server.BootstrapConfigurationError):
                    self.server.CpkServerBootstrapConfiguration.from_environment(environment)

    def test_workspace_mode_and_policy_input_are_closed_bounded_and_redacted(self):
        environment = self.environment()
        alternatives = ({**environment, "CPK_WORKSPACE_AUTHORITY": "other"},
            {name: value for name, value in environment.items() if name != "CPK_WORKSPACE_AUTHORITY"},
            {name: value for name, value in environment.items()
                if name != "CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE"})
        for value in alternatives:
            with self.subTest(mode=value.get("CPK_WORKSPACE_AUTHORITY")):
                with self.assertRaises(self.server.BootstrapConfigurationError):
                    self.server.CpkServerBootstrapConfiguration.from_environment(value)
        identities = [self.administrator.descriptor(), *(replace(self.administrator,
            subject_id="identity-" + str(index)).descriptor() for index in range(1024))]
        documents = (
            {**self.policy_document, "schema": "unknown"},
            {**self.policy_document, "workspace_grants": "private-input"},
            {**self.policy_document, "installation_id": float("nan")},
            {**self.policy_document, "administrators": []},
            {**self.policy_document, "known_identities": []},
            {**self.policy_document, "known_identities": self.policy_document["known_identities"] * 2},
            {**self.policy_document, "known_identities": identities},
            {**self.policy_document, "administrators": identities, "known_identities": identities},
            {**self.policy_document, "administrators": [replace(self.administrator, subject_id="unknown").descriptor()]},
            {**self.policy_document, "administrators": [{**self.administrator.descriptor(), "extra": True}]},
            {**self.policy_document, "capabilities": ["installed-management-a"] * 2},
            {**self.policy_document, "capabilities": ["capability-" + str(index) for index in range(65)]},
        )
        raws = [json.dumps(value) for value in documents]
        raws.extend((" " * (1_048_576 + 1),
            json.dumps(self.policy_document).replace('"schema":', '"schema":"duplicate","schema":', 1)))
        for raw in raws:
            self.policy_path.write_text(raw, encoding="utf-8")
            with self.subTest(length=len(raw)):
                with self.assertRaises(self.server.BootstrapConfigurationError) as caught:
                    self.configuration()
                self.assertNotIn("private-input", str(caught.exception))
                self.assertIsNone(caught.exception.__context__)
        self.write(self.policy_path, self.policy_document)
        link = self.root / "policy-link.json"
        link.symlink_to(self.policy_path)
        with self.assertRaises(self.server.BootstrapConfigurationError):
            self.server.CpkServerBootstrapConfiguration.from_environment({**environment,
                "CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE": str(link)})

    def test_dynamic_health_input_stays_unbound_until_real_post_receipt_factory(self):
        from control_plane_kit_servers_cpk_server.managed_health_placement import DockerRuntimeClientSelector
        config = self.configuration(health=True)
        process = config.managed_health_process
        self.assertIsNone(process.provider_clients)
        self.assertEqual(tuple(binding.capability.capability_id for binding in process.capability_bindings),
            ("installed-management-a",))
        self.assertTrue(all(binding.local_client_config is process.local_client_config
            for binding in process.capability_bindings))
        self.assertFalse(hasattr(process, "unit_of_work_factory"))
        actual_factory = self.server.OperationsApplicationFactory
        factories, order = [], []
        provider = self.server._SecretProviderComposition(authorized_resolver=Mock(), secret_custodian=Mock())
        def installation(*args, **kwargs):
            order.append("receipt")
            return object()
        def build_provider(value):
            self.assertEqual(order, ["receipt"])
            order.append("provider")
            return provider
        def factory(*args, **kwargs):
            value = actual_factory(*args, **kwargs)
            factories.append(value)
            return value
        with patch.object(self.server, "_install_operations_schema"), \
                patch.object(WorkspacePermissionReadService, "installation", side_effect=installation), \
                patch.object(self.server, "_secret_provider_composition", side_effect=build_provider), \
                patch.object(self.server, "OperationsApplicationFactory", side_effect=factory), \
                patch.object(self.server.psycopg, "connect") as connect, \
                patch("docker.DockerClient") as constructor, patch("docker.from_env") as ambient:
            application = self.server._operations_application(config)
        self.assertIsNotNone(application)
        self.assertEqual(len(factories), 1)
        composed = factories[0]
        bridge = composed.ports.managed_health.adapter
        selector = bridge.provider_clients
        self.assertIs(type(selector), DockerRuntimeClientSelector)
        self.assertIs(selector.unit_of_work_factory, composed.unit_of_work_factory)
        self.assertEqual(selector.capability_policy, config.workspace_authority.capability_policy)
        self.assertIs(bridge.native.provider_clients, selector)
        self.assertTrue(bridge.reader.require_invocations)
        connect.assert_not_called()
        constructor.assert_not_called()
        ambient.assert_not_called()

    def test_missing_receipt_stops_dynamic_process_before_effect_composition(self):
        config = self.configuration(health=True)
        with patch.object(self.server, "_install_operations_schema"), \
                patch.object(WorkspacePermissionReadService, "installation", side_effect=RuntimeError("private receipt")), \
                patch.object(self.server, "_secret_provider_composition") as provider, \
                patch.object(self.server, "_operations_effect_ports") as effects:
            with self.assertRaises(self.server.BootstrapConfigurationError) as caught:
                self.server._operations_application(config)
        self.assertNotIn("private receipt", str(caught.exception))
        provider.assert_not_called()
        effects.assert_not_called()

    def test_process_modes_and_installation_artifacts_cannot_mislabel_v2(self):
        v1 = {name: value for name, value in self.health_document.items() if name != "capability_ids"}
        v1.update(schema="cpk-server.managed-health.v1", scopes=[{"workspace_id": "workspace-a",
            "runtime_id": "runtime-a", "authority_ref": "authority-a"}])
        for mode, document in (("docker-unix-v1", self.health_document), ("docker-unix-v2", v1)):
            self.write(self.health_path, document)
            with self.subTest(mode=mode):
                with self.assertRaises(self.server.BootstrapConfigurationError):
                    self.server.CpkServerBootstrapConfiguration.from_environment({**self.environment(health=True),
                        "CPK_MANAGED_HEALTH": mode})
        self.write(self.health_path, v1)
        with self.assertRaises(self.server.BootstrapConfigurationError):
            self.server.CpkServerBootstrapConfiguration.from_environment({**self.environment(health=True),
                "CPK_MANAGED_HEALTH": "docker-unix-v1"})
        self.write(self.health_path, self.health_document)
        without_workspace_policy = {name: value for name, value in self.environment(health=True).items()
            if not name.startswith("CPK_WORKSPACE_AUTHORITY")}
        with self.assertRaises(self.server.BootstrapConfigurationError):
            self.server.CpkServerBootstrapConfiguration.from_environment(without_workspace_policy)
        a, b = "installed-management-a", "installed-management-b"
        for installed, workspace in (((a,), (b,)), ((a,), (a, b)), ((a, b), (a,))):
            self.write(self.health_path, {**self.health_document, "capability_ids": installed})
            self.write(self.policy_path, {**self.policy_document, "capabilities": workspace})
            with self.subTest(installed=installed, workspace=workspace):
                with self.assertRaises(self.server.BootstrapConfigurationError):
                    self.configuration(health=True)
        self.write(self.policy_path, self.policy_document)
        raw = json.dumps(self.health_document).encode()
        artifact = ConfigurationArtifact(self.health_api.MANAGED_HEALTH_ARTIFACT_ID,
            self.health_api.MANAGED_HEALTH_CONFIGURATION_PATH, ConfigurationMediaType.JSON,
            raw.decode(), ConfigurationFileMode.READ_ONLY)
        for call in (lambda: self.health_api.managed_health_configuration_artifact(raw),
                lambda: self.health_api._managed_health_configuration_from_artifact(artifact)):
            with self.assertRaises(ValueError) as caught:
                call()
            self.assertEqual(str(caught.exception), "managed health installation configuration is invalid")
        self.assertIsNotNone(self.health_api.managed_health_configuration_artifact(json.dumps(v1).encode()))
