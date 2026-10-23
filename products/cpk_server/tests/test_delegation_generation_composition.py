"""Thin provider generation and optional factory composition; no live effects."""
import importlib
import importlib.util
import inspect
from dataclasses import fields
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.identity import AuthenticatedPrincipal, PrincipalIdentity, PrincipalKind, WorkspaceGrant
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.secrets import (
    SecretCustodyGrant, SecretProviderEndpointReference, SecretReference, health_signing_intent_for,
)
from control_plane_kit_interpreters.secret_provider import SecretProviderBootstrapRegistry
from control_plane_kit_interpreters.secret_provider.client import SecretProviderClientPolicy
from control_plane_kit_operations import CpkServerApplicationError
from control_plane_kit_operations.delegation_key_generation import DelegationKeyGenerationGrant

from test_secret_provider_bootstrap import _provider_environment


class ProviderGenerationCompositionTests(unittest.TestCase):
    def adapter_module(self):
        name = "control_plane_kit_servers_cpk_server.delegation_key_generation"
        self.assertIsNotNone(importlib.util.find_spec(name), "provider generation bridge is not implemented")
        module = importlib.import_module(name)
        self.assertTrue(hasattr(module, "_ProviderDelegationKeyGenerator"))
        return module

    def grant(self):
        purpose = DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ
        custody = SecretCustodyGrant(
            custody_id="scust_" + "a" * 64, workspace_id="workspace-a",
            provider_registration_id="sprov_" + "b" * 64,
            endpoint_reference=SecretProviderEndpointReference("provider-main"),
            credential_reference=SecretReference("secret://bootstrap/provider-token"),
            reference=SecretReference("secret://provider-main/health/key"),
            intent=health_signing_intent_for(purpose), actor_subject="operator-a",
            correlation_id="generation-request", custody_fingerprint="d" * 64)
        return DelegationKeyGenerationGrant(custody, purpose, "issuer-a", "2026-10-23T00:00:00Z")

    def test_public_client_mapping_passthrough_and_no_constructor_io(self):
        module = self.adapter_module()
        grant = self.grant()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-provider-token"
            registry = SecretProviderBootstrapRegistry(
                endpoints={grant.custody_grant.endpoint_reference: "https://provider.invalid"},
                credential_files={grant.custody_grant.credential_reference: path})
            policy, transport = SecretProviderClientPolicy(), object()
            with patch.object(module, "ControlPlaneKitSecretsClient") as client, \
                    patch.object(SecretProviderBootstrapRegistry, "configuration_for",
                                 autospec=True, wraps=None) as configuration:
                expected = object()
                configuration.return_value = expected
                adapter = module._ProviderDelegationKeyGenerator(registry, policy=policy, transport=transport)
                configuration.assert_not_called()
                client.assert_not_called()
            # Use the real registry selection; the public client is the single IO boundary.
            expected = registry.configuration_for(endpoint_reference=grant.custody_grant.endpoint_reference,
                                                  credential_reference=grant.custody_grant.credential_reference)
            result = object()
            with patch.object(module, "ControlPlaneKitSecretsClient") as client:
                client.return_value.generate_delegation_key.return_value = result
                self.assertIs(adapter.generate(grant), result)
                client.assert_called_once_with(expected, policy=policy, transport=transport)
                client.return_value.generate_delegation_key.assert_called_once_with(
                    workspace_id=grant.workspace_id, reference=grant.reference,
                    purpose=grant.purpose, issuer=grant.issuer,
                    caller_subject=grant.actor_subject, correlation_id=grant.correlation_id)
            self.assertFalse(path.exists(), "adapter must not create/read credential material during construction")
            failure = RuntimeError("synthetic provider refusal")
            with patch.object(module, "ControlPlaneKitSecretsClient") as client:
                client.return_value.generate_delegation_key.side_effect = failure
                with self.assertRaises(RuntimeError) as raised:
                    adapter.generate(grant)
                self.assertIs(raised.exception, failure)
                self.assertEqual(client.return_value.generate_delegation_key.call_count, 1)

    def test_real_provider_composition_and_ports_share_registry_transport(self):
        server = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        with tempfile.TemporaryDirectory() as directory:
            config = server.CpkServerBootstrapConfiguration.from_environment({
                **_provider_environment(Path(directory) / "unopened-token"),
                "CPK_RUNTIME_INTERPRETERS": "none"})
            transport = object()
            provider = server._secret_provider_composition(config, transport=transport)
            generator = getattr(provider, "delegation_key_generator", None)
            self.assertIsNotNone(generator, "production provider composition omits generation")
            self.assertIs(generator.bootstrap_registry, provider.bootstrap_registry)
            self.assertIs(generator.transport, transport)
            ports = server._operations_effect_ports(config, provider)
            self.assertIs(ports.delegation_key_generator, generator)
            disabled = server._operations_effect_ports(config, server._SecretProviderComposition())
            self.assertIsNone(disabled.delegation_key_generator)


class GenerationFactoryAvailabilityTests(unittest.TestCase):
    def test_four_availability_cases_and_provision_always_unavailable(self):
        composition = importlib.import_module("control_plane_kit_servers_cpk_server.operations_application")
        boundary = importlib.import_module("control_plane_kit_servers_cpk_server.boundary")
        self.assertIn("delegation_key_generator", {item.name for item in fields(composition.OperationsEffectPorts)})
        self.assertIn("principal_authorizer", inspect.signature(composition.OperationsApplicationFactory).parameters)
        owner = getattr(composition, "DelegationKeyGenerationCommandService", None)
        self.assertIsNotNone(owner, "factory has no accepted generation service")
        principal = AuthenticatedPrincipal(PrincipalIdentity("issuer-a", "operator-a", PrincipalKind.OPERATOR),
                                          (WorkspaceGrant("workspace-a", tuple(PolicyScope)),))
        payload = dict(request_id="request-a", provider_registration_id="provider-a",
                       secret_reference="secret://provider/key", purpose="workload-node-health-read", issuer="")
        for has_generator, has_authority in ((False, False), (False, True), (True, False), (True, True)):
            with self.subTest(generator=has_generator, authority=has_authority):
                uow = Mock(side_effect=AssertionError("malformed/unavailable request must not open UoW"))
                generator = Mock() if has_generator else None
                authority = Mock() if has_authority else None
                clock = Mock(return_value="2026-10-23T00:00:00Z")
                ports = composition.OperationsEffectPorts(None, None, None, Mock(), Mock(),
                    disabled_runtime_adapter=Mock(), delegation_key_generator=generator)
                ids = composition.OperationsIdFactories(*(Mock() for _ in range(5)))
                with patch.object(composition, "DelegationKeyGenerationCommandService", wraps=owner) as service:
                    app = composition.OperationsApplicationFactory(uow, ports, ids, clock=clock,
                                                                  principal_authorizer=authority)()
                    if has_generator and has_authority:
                        service.assert_called_once_with(uow, generator, authorizer=authority, clock=clock)
                    else:
                        service.assert_not_called()
                request = boundary.CpkServerServiceRequest("http", "command.delegation-key.generate",
                    ControlPlaneServiceRole.EXECUTION, {"workspace_id": "workspace-a"}, payload, principal)
                with self.assertRaises(CpkServerApplicationError) as raised:
                    app.handle(request)
                # Closed fields pass initial routing. Empty issuer is rejected by the configured owner;
                # absent service stops first with 501, without entering that command constructor.
                self.assertEqual(raised.exception.status, 400 if has_generator and has_authority else 501)
                provision = boundary.CpkServerServiceRequest("http", "command.secret-material.provision",
                    ControlPlaneServiceRole.EXECUTION, {"workspace_id": "workspace-a"}, {}, principal)
                with self.assertRaises(CpkServerApplicationError) as raised:
                    app.handle(provision)
                self.assertEqual(raised.exception.status, 501)
                uow.assert_not_called()
                if generator is not None:
                    generator.generate.assert_not_called()
                if authority is not None:
                    authority.authorize.assert_not_called()
