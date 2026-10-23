"""Configured authority laws; synthetic identities and no provider effects."""
import importlib
import json
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_core.identity import (
    AuthenticatedPrincipal, IdentityContractError, PrincipalIdentity,
    PrincipalKind, WorkspaceGrant,
)
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.policies import PolicyScope

from cpk_http_host_fixtures import fixture
from test_http_mcp_boundaries import RecordingService
from test_secret_provider_bootstrap import _base_environment


READ = PolicyScope.DELEGATION_KEY_READ
GENERATE = PolicyScope.DELEGATION_KEY_GENERATE
REGISTER = PolicyScope.DELEGATION_KEY_REGISTER


def principal(*scopes, issuer="issuer-a", subject="operator-a",
              kind=PrincipalKind.OPERATOR, workspace="workspace-a"):
    return AuthenticatedPrincipal(PrincipalIdentity(issuer, subject, kind),
                                  (WorkspaceGrant(workspace, tuple(scopes)),))


class ConfiguredPrincipalAuthorityTests(unittest.TestCase):
    def authorizer(self, *policies):
        auth = importlib.import_module("control_plane_kit_servers_cpk_server.authentication")
        factory = getattr(auth, "ConfiguredPrincipalAuthorizer", None)
        self.assertIsNotNone(factory, "configured policy authority is not implemented")
        return factory(tuple(policies))

    def test_policy_intersects_original_ceiling_without_mutating_request(self):
        request = principal(READ, GENERATE)
        authority = self.authorizer(principal(GENERATE, REGISTER))
        result = authority.authorize(request, "workspace-a")
        self.assertEqual(result.principal.identity, request.identity)
        self.assertEqual(result.workspace_id, "workspace-a")
        self.assertEqual(result.granted_scopes, (GENERATE,))
        self.assertEqual(result.principal.workspace_grants,
                         (WorkspaceGrant("workspace-a", (GENERATE,)),))
        self.assertEqual(request, principal(READ, GENERATE))
        self.assertEqual(authority.authorize(principal(REGISTER), "workspace-a").granted_scopes,
                         (REGISTER,))
        self.assertEqual(authority.authorize(principal(READ), "workspace-a").granted_scopes, ())
        self.assertEqual(self.authorizer(principal()).authorize(request, "workspace-a").granted_scopes, ())

    def test_equal_normalized_duplicates_collapse(self):
        left = AuthenticatedPrincipal(principal().identity, (
            WorkspaceGrant("workspace-b", (READ,)),
            WorkspaceGrant("workspace-a", (REGISTER, GENERATE))))
        right = AuthenticatedPrincipal(left.identity, (
            WorkspaceGrant("workspace-a", (GENERATE, REGISTER)),
            WorkspaceGrant("workspace-b", (READ,))))
        for policies in ((left, right), (right, left), (left, right, left)):
            with self.subTest(policies=policies):
                result = self.authorizer(*policies).authorize(principal(GENERATE), "workspace-a")
                self.assertEqual(result.granted_scopes, (GENERATE,))

    def test_conflicts_deny_whole_identity_in_every_order_and_cannot_recover(self):
        left = principal(GENERATE)
        for right in (principal(REGISTER), principal(GENERATE, workspace="workspace-b")):
            for policies in ((left, right), (right, left), (left, right, left), (right, left, right)):
                with self.subTest(policies=policies):
                    authority = self.authorizer(*policies)
                    for workspace in ("workspace-a", "workspace-b"):
                        with self.assertRaises(IdentityContractError):
                            authority.authorize(principal(GENERATE, REGISTER, workspace=workspace), workspace)

    def test_full_identity_workspace_and_missing_source_fail_closed(self):
        authority = self.authorizer(principal(GENERATE))
        for request, workspace in (
            (principal(GENERATE, issuer="issuer-b"), "workspace-a"),
            (principal(GENERATE, subject="operator-b"), "workspace-a"),
            (principal(GENERATE, kind=PrincipalKind.SERVICE), "workspace-a"),
            (principal(GENERATE, workspace="workspace-b"), "workspace-b"),
            (principal(GENERATE), "workspace-b"),
        ):
            with self.subTest(request=request, workspace=workspace), self.assertRaises(IdentityContractError):
                authority.authorize(request, workspace)
        with self.assertRaises(IdentityContractError):
            self.authorizer().authorize(principal(GENERATE), "workspace-a")
        isolated = self.authorizer(principal(GENERATE), principal(READ, issuer="issuer-b"),
                                   principal(REGISTER, kind=PrincipalKind.SERVICE))
        self.assertEqual(isolated.authorize(principal(READ, GENERATE, issuer="issuer-b"),
                                           "workspace-a").granted_scopes, (READ,))
        self.assertEqual(isolated.authorize(principal(GENERATE, REGISTER, kind=PrincipalKind.SERVICE),
                                           "workspace-a").granted_scopes, (REGISTER,))

    def test_replacement_configuration_changes_policy_without_claiming_reload(self):
        request = principal(GENERATE, REGISTER)
        original = self.authorizer(principal(GENERATE))
        replacement = self.authorizer(principal(REGISTER))
        self.assertEqual(original.authorize(request, "workspace-a").granted_scopes, (GENERATE,))
        self.assertEqual(replacement.authorize(request, "workspace-a").granted_scopes, (REGISTER,))
        self.assertEqual(original.authorize(request, "workspace-a").granted_scopes, (GENERATE,))


class ConfiguredAuthorityStartupTests(unittest.TestCase):
    def config(self, *, multi=False):
        server = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        environment = {**_base_environment(), "CPK_RUNTIME_INTERPRETERS": "none",
                       "CPK_CONTROL_AUTH_VERIFIER": "static-development"}
        grants = {"workspace-a": [GENERATE.value, REGISTER.value]}
        if multi:
            environment["CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"] = json.dumps([
                {"credential": "synthetic-operator-token", "subject_id": "operator-a",
                 "kind": "operator", "workspace_grants": grants}])
        else:
            environment.update(CPK_CONTROL_AUTH_STATIC_CREDENTIAL="synthetic-operator-token",
                CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON=json.dumps(grants))
        return server, server.CpkServerBootstrapConfiguration.from_environment(environment)

    def configured(self, server, config):
        factory = getattr(server, "_configured_principal_authorizer", None)
        self.assertIsNotNone(factory, "startup has no independent configured authority")
        return factory(config)

    def test_single_and_multi_config_project_only_credential_free_policy(self):
        for multi in (False, True):
            with self.subTest(multi=multi):
                server, config = self.config(multi=multi)
                request = server._credential_verifier(config).authenticate(b"synthetic-operator-token")
                authority = self.configured(server, config)
                result = authority.authorize(request, "workspace-a")
                self.assertEqual(result.principal.identity, request.identity)
                self.assertEqual(set(result.granted_scopes), {GENERATE, REGISTER})
                self.assertNotIn("synthetic-operator-token", repr(authority))
                # The projected directory accepts principals, never verifier/credential records.
                auth = importlib.import_module("control_plane_kit_servers_cpk_server.authentication")
                with self.assertRaises((TypeError, ValueError)):
                    type(authority)((auth.StaticDevelopmentPrincipalCredential(
                        b"synthetic-operator-token", request),))

    def test_main_passes_real_configured_authority_through_real_create_app(self):
        server, config = self.config(multi=True)
        services = {role: RecordingService(role.value) for role in ControlPlaneServiceRole}
        with patch.object(server.CpkServerBootstrapConfiguration, "from_environment", return_value=config), \
                patch.object(server, "read_cpk_control_configuration", return_value=fixture().config), \
                patch.object(server, "_operations_application", return_value=Mock(services=services)) as application, \
                patch.object(server.uvicorn, "run") as run:
            self.assertEqual(server.main(), 0)
        authority = application.call_args.kwargs.get("principal_authorizer")
        self.assertIsNotNone(authority, "main/create_app dropped configured permission authority")
        request = server._credential_verifier(config).authenticate(b"synthetic-operator-token")
        self.assertEqual(set(authority.authorize(request, "workspace-a").granted_scopes), {GENERATE, REGISTER})
        run.assert_called_once()

    def test_injected_verifier_has_no_implicit_policy_and_explicit_authority_is_forwarded(self):
        server, config = self.config()
        services = {role: RecordingService(role.value) for role in ControlPlaneServiceRole}
        verifier = server._credential_verifier(config)
        with patch.object(server, "_operations_application", return_value=Mock(services=services)) as application:
            server.create_app(config, verifier, control=fixture().config)
            self.assertIsNone(application.call_args.kwargs.get("principal_authorizer"))
            authority = self.configured(server, config)
            server.create_app(config, verifier, control=fixture().config, principal_authorizer=authority)
            self.assertIs(application.call_args.kwargs.get("principal_authorizer"), authority)
