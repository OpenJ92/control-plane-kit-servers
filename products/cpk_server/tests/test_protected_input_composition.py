"""#317 optional custody wiring through the actual Operations factory."""
from dataclasses import fields
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_core.identity import AuthenticatedPrincipal, PrincipalIdentity, PrincipalKind, WorkspaceGrant
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations import CpkServerApplicationError
from control_plane_kit_operations.health_receiver_trust import HealthReceiverDecoders

from test_secret_provider_bootstrap import _provider_environment


class ProtectedInputCompositionTests(unittest.TestCase):
    def test_actual_provider_custodian_reaches_effect_ports_without_io(self):
        server = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        with TemporaryDirectory() as directory:
            token = Path(directory) / "unopened-token"
            config = server.CpkServerBootstrapConfiguration.from_environment({
                **_provider_environment(token), "CPK_RUNTIME_INTERPRETERS": "none"})
            transport = object()
            provider = server._secret_provider_composition(config, transport=transport)
            self.assertIsNotNone(provider.secret_custodian)
            ports = server._operations_effect_ports(config, provider)
            self.assertIs(getattr(ports, "secret_custodian", None), provider.secret_custodian,
                          "production effect ports omit the existing provider custodian")
            self.assertFalse(token.exists())
            disabled = server._operations_effect_ports(config, server._SecretProviderComposition())
            self.assertIsNone(disabled.secret_custodian)

    def test_custody_and_authority_matrix_uses_exact_owner_uow_and_clock(self):
        factory = importlib.import_module("control_plane_kit_servers_cpk_server.operations_application")
        boundary = importlib.import_module("control_plane_kit_servers_cpk_server.boundary")
        auth = importlib.import_module("control_plane_kit_servers_cpk_server.authentication")
        self.assertIn("secret_custodian", {item.name for item in fields(factory.OperationsEffectPorts)},
                      "the shared factory has no explicit custody port")
        owner = getattr(factory, "SecretMaterialProvisionCommandService", None)
        self.assertIsNotNone(owner, "the accepted provision owner is not composed")
        principal = AuthenticatedPrincipal(PrincipalIdentity("issuer-a", "operator-a", PrincipalKind.OPERATOR),
            (WorkspaceGrant("workspace-a", tuple(PolicyScope)),))
        for custody_present, authority_present in ((False, False), (False, True), (True, False), (True, True)):
            with self.subTest(custody=custody_present, authority=authority_present):
                uow = Mock(side_effect=AssertionError("unavailable/malformed request opened a unit of work"))
                custody = Mock() if custody_present else None
                authority = auth.ConfiguredPrincipalAuthorizer((principal,)) if authority_present else None
                clock = Mock(return_value="2026-10-23T00:00:00Z")
                ports = factory.OperationsEffectPorts(None, None, None, HealthReceiverDecoders(()), Mock(),
                    disabled_runtime_adapter=Mock(), secret_custodian=custody)
                ids = factory.OperationsIdFactories(*(Mock() for _ in range(5)))
                with patch.object(factory, "SecretMaterialProvisionCommandService", wraps=owner) as constructor:
                    app = factory.OperationsApplicationFactory(uow, ports, ids, clock=clock,
                        principal_authorizer=authority)()
                if custody_present and authority_present:
                    constructor.assert_called_once_with(uow, custody, authorizer=authority, clock=clock)
                else:
                    constructor.assert_not_called()
                request = boundary.CpkServerServiceRequest("http", "command.secret-material.provision",
                    ControlPlaneServiceRole.EXECUTION, {"workspace_id": "workspace-a"}, {}, principal)
                with self.assertRaises(CpkServerApplicationError) as failure:
                    app.handle(request)
                self.assertEqual(failure.exception.status, 400 if custody_present and authority_present else 501)
                uow.assert_not_called()
                if custody is not None:
                    self.assertEqual(custody.mock_calls, [])

    def test_independent_current_policy_denies_before_decoder_and_custody(self):
        factory = importlib.import_module("control_plane_kit_servers_cpk_server.operations_application")
        boundary = importlib.import_module("control_plane_kit_servers_cpk_server.boundary")
        auth = importlib.import_module("control_plane_kit_servers_cpk_server.authentication")
        self.assertIn("secret_custodian", {item.name for item in fields(factory.OperationsEffectPorts)})
        identity = PrincipalIdentity("issuer-a", "operator-a", PrincipalKind.OPERATOR)
        request_principal = AuthenticatedPrincipal(identity, (WorkspaceGrant("workspace-a", tuple(PolicyScope)),))
        policy_principal = AuthenticatedPrincipal(identity, (WorkspaceGrant("workspace-a", (PolicyScope.SECRET_PROVIDER_REGISTER,)),))
        uow = Mock(side_effect=AssertionError("denied request opened a unit of work"))
        custody = Mock()
        ports = factory.OperationsEffectPorts(None, None, None, HealthReceiverDecoders(()), Mock(),
            disabled_runtime_adapter=Mock(), secret_custodian=custody)
        ids = factory.OperationsIdFactories(*(Mock() for _ in range(5)))
        app = factory.OperationsApplicationFactory(uow, ports, ids,
            principal_authorizer=auth.ConfiguredPrincipalAuthorizer((policy_principal,)))()
        # Malformed ordinary input would be 400 if decoding preceded current policy.
        request = boundary.CpkServerServiceRequest("http", "command.secret-material.provision",
            ControlPlaneServiceRole.EXECUTION, {"workspace_id": "workspace-a"}, {}, request_principal)
        with self.assertRaises(CpkServerApplicationError) as failure:
            app.handle(request)
        self.assertEqual(failure.exception.status, 403)
        self.assertEqual(custody.mock_calls, [])
        uow.assert_not_called()
