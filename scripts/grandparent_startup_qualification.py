"""Real main/factory wiring with predecoded owner support, not file/live proof."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_servers_cpk_server import server
from control_plane_kit_servers_cpk_server import operations_application as application
import control_plane_kit_operations.workspace_permissions as permissions
import test_dynamic_effect_composition as dynamic_fixture
import scripts.managed_verification_composition_qualification as managed_fixture
from cpk_http_host_fixtures import fixture as receiving_fixture
from test_http_mcp_boundaries import DeterministicVerifier


class GrandparentStartupCompositionTests(unittest.TestCase):
    def test_ordinary_main_builds_real_factory_with_single_registered_sender(self):
        owner = managed_fixture.ManagedCompositionTests()
        owner.setUp()
        support = owner.support
        config, _ = dynamic_fixture.DynamicEffectCompositionTests().configuration()
        config = replace(config, mcp_profile="grandparent-read-only-v1",
            http_sample_support=support.http_samples, managed_verification_support=support)
        factories, constructions = [], {}
        real_factory = server.OperationsApplicationFactory

        def factory(*args, **kwargs):
            value = real_factory(*args, **kwargs)
            factories.append(value)
            return value

        def delegate(name):
            original = getattr(application, name)
            def construct(*args, **kwargs):
                value = original(*args, **kwargs)
                constructions.setdefault(name, []).append((args, kwargs, value))
                return value
            return construct

        def forbidden(*_args, **_kwargs):
            raise AssertionError("startup composition must not access external state")

        custodian = Mock(spec_set=("store", "revoke"))
        custodian.store.side_effect = forbidden
        custodian.revoke.side_effect = forbidden
        provider = server._SecretProviderComposition(
            authorized_resolver=SimpleNamespace(resolve=forbidden),
            secret_custodian=custodian)
        with patch.object(server.CpkServerBootstrapConfiguration, "from_environment", return_value=config), \
                patch.object(server, "read_cpk_control_configuration", return_value=receiving_fixture().config), \
                patch.object(server, "read_cpk_http_sample_binding", return_value=None), \
                patch.object(server, "_credential_verifier", return_value=DeterministicVerifier()), \
                patch.object(server, "_install_operations_schema"), \
                patch.object(permissions.WorkspacePermissionReadService, "installation"), \
                patch.object(server.psycopg, "connect", side_effect=forbidden), \
                patch.object(server, "_secret_provider_composition", return_value=provider), \
                patch.object(server, "OperationsApplicationFactory", side_effect=factory), \
                patch.object(application, "ExecutionAdmissionCommandService", side_effect=delegate("ExecutionAdmissionCommandService")), \
                patch.object(application, "ExecutionInvocationService", side_effect=delegate("ExecutionInvocationService")), \
                patch.object(application, "RuntimeInterpreterDispatcher", side_effect=delegate("RuntimeInterpreterDispatcher")), \
                patch.object(server.uvicorn, "run") as listen:
            self.assertEqual(server.main(), 0)
        self.assertEqual(custodian.mock_calls, [])
        listen.assert_called_once()
        self.assertIsNotNone(listen.call_args.args[0].state.http_boundary)
        self.assertIsNotNone(listen.call_args.args[0].state.mcp_boundary)
        actual_factory, = factories
        registration = actual_factory.ports.runtime_interpreters[RuntimeKind.DOCKER]
        self.assertIs(registration.managed_verification_support, support)
        self.assertIs(registration.http_sample_support, support.http_samples)
        for name in ("ExecutionAdmissionCommandService", "ExecutionInvocationService"):
            (_, kwargs, _), = constructions[name]
            self.assertIs(kwargs["managed_verification_registration"], registration)
            self.assertIs(kwargs["http_sample_registration"], registration)
            self.assertIs(kwargs["managed_verification_support"], support)
        (args, _, dispatcher), = constructions["RuntimeInterpreterDispatcher"]
        self.assertIs(args[0][RuntimeKind.DOCKER], registration)
        self.assertIs(dispatcher.interpreters[RuntimeKind.DOCKER], registration)
