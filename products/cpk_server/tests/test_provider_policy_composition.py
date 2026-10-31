"""Servers admission/framing and real owner/client composition, with synthetic IO."""
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import MagicMock, Mock, patch

import httpx
from control_plane_kit_core.identity import AuthenticatedPrincipal, PrincipalIdentity, PrincipalKind
from control_plane_kit_core.secrets import SecretProviderEndpointReference, SecretReference
from control_plane_kit_interpreters.secret_provider import (
    ControlPlaneKitSecretsPolicyClient, SecretProviderClientConfiguration,
)
from control_plane_kit_operations.provider_policy_commands import (
    ProviderPolicyAdmission, ProviderPolicyAdministrationPolicy, ProviderPolicyBinding,
)


class ProviderPolicyCompositionTests(unittest.TestCase):
    def setUp(self):
        self.config_module = importlib.import_module(
            "control_plane_kit_servers_cpk_server.provider_policy_configuration")
        self.composition = importlib.import_module(
            "control_plane_kit_servers_cpk_server.operations_application")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.credential = Path(self.directory.name) / "admin-credential"
        self.identity = PrincipalIdentity("issuer-a", "administrator-a", PrincipalKind.OPERATOR)
        self.binding = ProviderPolicyBinding("binding-a", "logical-a", "provider-a")
        self.policy = ProviderPolicyAdministrationPolicy("installation-a",
            (ProviderPolicyAdmission(self.identity, self.binding),))
        self.client_configuration = SecretProviderClientConfiguration(
            SecretProviderEndpointReference("policy-endpoint"), "https://provider.invalid",
            SecretReference("secret://provider/policy-admin"), self.credential)
        self.authority = self.config_module.ProviderPolicyAuthorityConfiguration(self.policy,
            (self.config_module.ProviderPolicyClientBinding(self.binding, self.client_configuration),))
        self.uow = MagicMock()
        self.requests = []

    def boundaries(self, authority=True):
        from control_plane_kit_operations.health_receiver_trust import HealthReceiverDecoders
        from control_plane_kit_servers_cpk_server.server import _UnsupportedExecutionAdapter
        from control_plane_kit_servers_cpk_server import (
            CpkServerApplicationBoundary, CpkServerHttpProcessBoundary, CpkServerMcpProcessBoundary,
            CpkServerProcessConfiguration, create_cpk_server_composition,
        )
        ports = self.composition.OperationsEffectPorts(None, None, None,
            HealthReceiverDecoders(()), object(), disabled_runtime_adapter=_UnsupportedExecutionAdapter())
        app = self.composition.OperationsApplicationFactory(self.uow, ports,
            self.composition.OperationsIdFactories(*(lambda: "unused" for _ in range(5))),
            clock=lambda: "2030-01-01T00:00:00Z",
            provider_policy_authority=self.authority if authority else None)()
        self.verifier = Mock()
        self.verifier.authenticate.return_value = AuthenticatedPrincipal(self.identity)
        shared = CpkServerApplicationBoundary(app, self.verifier)
        contract = create_cpk_server_composition(
            CpkServerProcessConfiguration.execution_capable(authentication_required=True))
        return CpkServerHttpProcessBoundary(contract, shared), CpkServerMcpProcessBoundary(contract, shared)

    def http(self, boundary, suffix="grants", *, method="GET", payload=None, query=b"", headers=None):
        return boundary.handle(method=method, path="/administration/provider-policies/logical-a/" + suffix,
            headers={"Authorization": "Bearer caller-token"} if headers is None else headers,
            body=b"" if payload is None else json.dumps(payload).encode(), query_string=query)

    def mcp(self, boundary, name="read.provider-policy-grants", **arguments):
        method = "tools/call" if name.startswith("command.") else "resources/read"
        return boundary.handle(headers={"Authorization": "Bearer caller-token",
            "Accept": "application/json", "MCP-Protocol-Version": "2025-06-18", "Mcp-Method": method},
            message={"jsonrpc": "2.0", "id": "policy", "method": method,
                "params": {"name": name, "arguments": {"logical_provider_id": "logical-a", **arguments}}})

    def provider(self, request):
        self.requests.append(request)
        if request.method == "POST":
            value = json.loads(request.content)
            revoked = request.url.path.endswith("/revoke")
            return httpx.Response(200, json={**value, "provider_id": "provider-a",
                "operation": "revoke" if revoked else "grant",
                "outcome": "revoked" if revoked else "granted",
                "code": "provider-policy-revoked" if revoked else "provider-policy-granted",
                "grant_id": "grant-a", "resulting_revision": value["expected_revision"] + 1,
                "actor": "provider-administrator", "occurred_at": "2030-01-01T00:00:00Z"})
        grant = {"subject": "client-a", "workspace_id": "workspace-a", "action": "secret.metadata",
            "intent": None, "grant_id": "grant-a", "provider_id": "provider-a", "origin": "command",
            "granted_by": "provider-administrator", "grant_correlation_id": "synthetic",
            "granted_at": "2030-01-01T00:00:00Z", "revoked_by": None,
            "revoke_correlation_id": None, "revoked_at": None}
        return httpx.Response(200, json={"revision": 1, **(
            {"grant": grant} if request.url.path.endswith("/grant-a")
            else {"grants": [grant], "next_after": None})})

    def clients(self, handler=None):
        self.credential.write_text("synthetic-independent-admin-token")
        return patch.object(self.config_module, "ControlPlaneKitSecretsPolicyClient",
            side_effect=lambda *args: ControlPlaneKitSecretsPolicyClient(*args,
                transport=httpx.MockTransport(handler or self.provider)))

    def test_real_factory_is_lazy_and_both_read_surfaces_use_fixed_independent_client(self):
        with self.clients() as acquire:
            http, mcp = self.boundaries()
            acquire.assert_not_called()
            self.uow.assert_not_called()
            responses = (self.http(http, query=b"subject=client-a&workspace_id=workspace-a&action=secret.metadata&limit=2"),
                self.mcp(mcp, subject="client-a", workspace_id="workspace-a", action="secret.metadata", limit=2),
                self.http(http, "grants/grant-a"),
                self.mcp(mcp, "read.provider-policy-grant", grant_id="grant-a"))
            self.assertEqual([response.status for response in responses], [200] * 4)
            self.assertEqual(acquire.call_count, 4)
        self.uow.assert_not_called()
        for request in self.requests:
            self.assertEqual(request.url.host, "provider.invalid")
            self.assertEqual(request.headers["authorization"], "Bearer synthetic-independent-admin-token")
            self.assertNotIn("caller-token", repr(request.headers))
        self.assertEqual(self.requests[0].url, self.requests[1].url)

    def test_authentication_and_independent_identity_denials_never_acquire(self):
        with patch.object(self.config_module, "ControlPlaneKitSecretsPolicyClient") as acquire:
            http, mcp = self.boundaries()
            self.assertEqual(self.http(http, headers={}).status, 401)
            for identity in (replace(self.identity, issuer="other-issuer"),
                    replace(self.identity, subject_id="workspace-administrator")):
                self.verifier.authenticate.return_value = AuthenticatedPrincipal(identity)
                self.assertEqual(self.http(http).status, 403)
                self.assertEqual(self.mcp(mcp).status, 403)
                self.assertEqual(self.http(http, method="POST", payload={"endpoint": "injected"}).status, 403)
            acquire.assert_not_called()
            self.uow.assert_not_called()
        self.assertFalse(self.credential.exists())

    def test_closed_query_and_injection_refusal_before_acquisition(self):
        with patch.object(self.config_module, "ControlPlaneKitSecretsPolicyClient") as acquire:
            http, mcp = self.boundaries()
            for query in (b"endpoint=private", b"limit=2&limit=3", b"subject=%FF", b"after=%7B%7D"):
                self.assertEqual(self.http(http, query=query).status, 400)
            for suffix in ("grants/grant-a", "commands/" + "a" * 64):
                self.assertEqual(self.http(http, suffix, query=b"limit=2").status, 400)
            for field in ("endpoint", "bearer", "actor", "binding", "method"):
                self.assertEqual(self.http(http, method="POST", payload={field: "injected"}).status, 400)
                self.assertEqual(self.mcp(mcp, **{field: "injected"}).status, 400)
            acquire.assert_not_called()
            self.uow.assert_not_called()

    def test_disabled_and_missing_or_changed_binding_fail_without_client(self):
        with patch.object(self.config_module, "ControlPlaneKitSecretsPolicyClient") as acquire:
            http, mcp = self.boundaries(authority=False)
            self.assertEqual(self.http(http).status, 404)
            self.assertEqual(self.mcp(mcp).status, 404)
            for changed in (replace(self.binding, provider_id="replacement-provider"),
                    replace(self.binding, logical_provider_id="replacement-logical")):
                with self.assertRaises(ValueError):
                    self.authority.port(changed)
            acquire.assert_not_called()
            self.authority = replace(self.authority, bindings=())
            http, mcp = self.boundaries()
            self.assertEqual(self.http(http).status, 503)
            self.assertEqual(self.mcp(mcp).status, 503)
            acquire.assert_not_called()
            self.uow.assert_not_called()

    def test_owner_errors_and_oversized_provider_output_are_bounded_on_both_surfaces(self):
        for status, payload in ((403, {"private": "private-provider-sentinel"}),
                (200, {"private": "x" * 1_100_000})):
            with self.subTest(status=status), self.clients(lambda request: httpx.Response(status, json=payload)):
                http, mcp = self.boundaries()
                for response in (self.http(http), self.mcp(mcp)):
                    self.assertIn(response.status, (403, 503))
                    encoded = json.dumps(response.body)
                    self.assertLess(len(encoded), 4096)
                    self.assertNotIn("private-provider-sentinel", encoded)
                    self.assertNotIn("synthetic-independent", encoded)

    def test_real_command_owner_dispatch_preserves_caller_and_uses_fixed_provider_credential(self):
        # Minimal store protocol fixture; persistence/replay/CAS remain Operations tests.
        store = self.uow.return_value.__enter__.return_value.stores.provider_policy_commands
        records = {}
        def reserve(record):
            records[record.command_id] = record
            return record
        def claim(command_id, *, claimed_at):
            records[command_id] = replace(records[command_id], dispatch_claimed_at=claimed_at)
            return records[command_id]
        def append(command_id, observation):
            records[command_id] = replace(records[command_id], observations=(observation,),
                observation_count=1, has_matching_result=observation.matches_intent)
            return records[command_id]
        store.reserve.side_effect = reserve
        store.claim.side_effect = claim
        store.append_observation.side_effect = append
        store.get.side_effect = records.__getitem__
        payload = {"coordinate": {"subject": "client-a", "workspace_id": "workspace-a",
            "action": "secret.metadata", "intent": None}, "expected_revision": 0, "idempotency_key": "grant-a"}
        with self.clients() as acquire:
            http, mcp = self.boundaries()
            response = self.http(http, method="POST", payload=payload)
            self.assertEqual(response.status, 200)
            response = self.mcp(mcp, "command.provider-policy.revoke", grant_id="grant-a",
                **{**payload, "expected_revision": 1, "idempotency_key": "revoke-a"})
            self.assertEqual(response.status, 200)
            self.assertEqual(acquire.call_count, 2)
            for command_id in records:
                self.assertEqual(self.http(http, "commands/" + command_id).status, 200)
                self.assertEqual(self.mcp(mcp, "read.provider-policy-command", command_id=command_id).status, 200)
                self.assertEqual(self.http(http, "commands/" + command_id + "/reconcile",
                    method="POST", payload={}).status, 200)
            self.assertEqual(acquire.call_count, 2)
            replacement = replace(self.binding, binding_id="replacement-binding")
            self.authority = self.config_module.ProviderPolicyAuthorityConfiguration(
                ProviderPolicyAdministrationPolicy("installation-a",
                    (ProviderPolicyAdmission(self.identity, replacement),)),
                (self.config_module.ProviderPolicyClientBinding(replacement, self.client_configuration),))
            http, mcp = self.boundaries()
            for command_id in records:
                self.assertEqual(self.http(http, "commands/" + command_id).status, 403)
                self.assertEqual(self.mcp(mcp, "command.provider-policy.reconcile", command_id=command_id).status, 403)
            self.assertEqual(acquire.call_count, 2)
        self.assertTrue(all(record.actor == self.identity for record in records.values()))
        self.assertEqual(len(self.requests), 2)
        for request in self.requests:
            self.assertEqual(request.headers["authorization"], "Bearer synthetic-independent-admin-token")
            self.assertNotIn("idempotency_key", json.loads(request.content))

    def installer_value(self):
        return {"schema": "cpk-server.provider-policy-authority.v1", "installation_id": "installation-a",
            "admissions": [{"identity": self.identity.descriptor(), "binding_id": "binding-a"}],
            "bindings": [{"binding_id": "binding-a", "logical_provider_id": "logical-a", "provider_id": "provider-a",
                "endpoint_reference": "policy-endpoint", "base_url": "https://provider.invalid",
                "credential_reference": "secret://provider/policy-admin", "credential_file": str(self.credential)}]}

    def test_installer_file_is_closed_bounded_and_does_not_read_credentials(self):
        value = self.installer_value()
        raw = json.dumps(value).encode()
        config = self.config_module.decode_provider_policy_authority_configuration(raw)
        self.assertEqual(config.administration_policy, self.policy)
        for private in ("provider.invalid", "policy-admin", "provider-a", str(self.credential)):
            self.assertNotIn(private, repr(config))
            self.assertNotIn(private, repr(config.bindings[0]))
        invalid = (b'{"schema":"x","schema":"y"}', raw[:-1] + b',"token":"private"}',
            b"x" * 1_048_577, b"[" * 1000, json.dumps({**value, "bindings": value["bindings"] * 2}).encode())
        for content in invalid:
            with self.assertRaises(ValueError) as caught:
                self.config_module.decode_provider_policy_authority_configuration(content)
            self.assertEqual(str(caught.exception), "provider-policy authority process configuration is invalid")
            self.assertIsNone(caught.exception.__context__)
        path = Path(self.directory.name) / "configuration.json"
        path.write_bytes(raw)
        observed = self.config_module.read_provider_policy_authority_configuration(str(path))
        self.assertEqual(observed.administration_policy, self.policy)
        link = path.with_name("link.json")
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            self.config_module.read_provider_policy_authority_configuration(str(link))
        self.assertFalse(self.credential.exists())

    def test_mismatched_installation_and_ambiguous_binding_reject_before_startup_effects(self):
        from control_plane_kit_servers_cpk_server import server
        from test_secret_provider_bootstrap import _base_environment
        from test_operations_application_factory import OperationsApplicationFactoryTests
        with self.assertRaises(ValueError):
            replace(self.authority, bindings=self.authority.bindings * 2)
        workspace = OperationsApplicationFactoryTests().workspace_authority()
        provider = replace(self.authority,
            administration_policy=replace(self.policy, installation_id="another-installation"))
        config = replace(server.CpkServerBootstrapConfiguration.from_environment(_base_environment()),
            workspace_authority=workspace, provider_policy_authority=provider)
        with patch.object(server, "_install_operations_schema") as schema, \
                patch.object(server, "_secret_provider_composition") as ordinary, \
                patch.object(self.config_module, "ControlPlaneKitSecretsPolicyClient") as acquire:
            with self.assertRaises(server.BootstrapConfigurationError):
                server._operations_application(config)
            schema.assert_not_called()
            ordinary.assert_not_called()
            acquire.assert_not_called()

    def test_process_activation_and_real_startup_forward_same_authority(self):
        from control_plane_kit_servers_cpk_server import server
        from test_secret_provider_bootstrap import _base_environment
        values = _base_environment()
        self.assertIsNone(server.CpkServerBootstrapConfiguration.from_environment(values).provider_policy_authority)
        path = Path(self.directory.name) / "configuration.json"
        path.write_text(json.dumps(self.installer_value()))
        enabled = {**values, "CPK_PROVIDER_POLICY_AUTHORITY": "secrets-v1",
            "CPK_PROVIDER_POLICY_AUTHORITY_CONFIGURATION_FILE": str(path)}
        config = server.CpkServerBootstrapConfiguration.from_environment(enabled)
        self.assertEqual(config.provider_policy_authority.administration_policy, self.policy)
        for extra in ({"CPK_PROVIDER_POLICY_AUTHORITY": "secrets-v1"},
                {"CPK_PROVIDER_POLICY_AUTHORITY_CONFIGURATION_FILE": str(path)},
                {"CPK_PROVIDER_POLICY_AUTHORITY": "unknown"}):
            with self.assertRaises(server.BootstrapConfigurationError):
                server.CpkServerBootstrapConfiguration.from_environment({**values, **extra})
        with patch.object(server, "_install_operations_schema"), \
                patch.object(server, "_secret_provider_composition"), \
                patch.object(server, "_operations_effect_ports"), \
                patch.object(server, "OperationsApplicationFactory") as factory:
            server._operations_application(config)
            self.assertIs(factory.call_args.kwargs["provider_policy_authority"], config.provider_policy_authority)
        self.assertFalse(self.credential.exists())

    def test_provider_only_process_authenticates_without_granting_workspace_access(self):
        from control_plane_kit_servers_cpk_server import server
        from control_plane_kit_servers_cpk_server import (
            CpkServerApplicationBoundary, CpkServerHttpProcessBoundary, CpkServerMcpProcessBoundary,
            create_cpk_server_composition,
        )
        from test_secret_provider_bootstrap import _base_environment
        from test_operations_application_factory import OperationsApplicationFactoryTests
        path = Path(self.directory.name) / "provider-only.json"
        for multiple in (False, True):
            with self.subTest(multiple=multiple):
                values = {**_base_environment(), "CPK_CONTROL_AUTH_VERIFIER": "static-development"}
                if multiple:
                    self.identity = server.static_development_principal(subject_id="provider-administrator",
                        kind=PrincipalKind.OPERATOR, workspace_grants=()).identity
                    values["CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"] = json.dumps([{
                        "credential": "caller-token", "subject_id": self.identity.subject_id,
                        "kind": "operator", "workspace_grants": {}}])
                else:
                    self.identity = server._static_operator_identity()
                    values.update(CPK_CONTROL_AUTH_STATIC_CREDENTIAL="caller-token",
                        CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON="{}")
                with self.assertRaises(server.BootstrapConfigurationError):
                    server.CpkServerBootstrapConfiguration.from_environment(values)
                path.write_text(json.dumps(self.installer_value()))
                config = server.CpkServerBootstrapConfiguration.from_environment({**values,
                    "CPK_PROVIDER_POLICY_AUTHORITY": "secrets-v1",
                    "CPK_PROVIDER_POLICY_AUTHORITY_CONFIGURATION_FILE": str(path)})
                self.assertIsNone(config.workspace_authority)
                verifier = server._credential_verifier(config)
                self.assertEqual(verifier.authenticate(b"caller-token").workspace_grants, ())
                ports = OperationsApplicationFactoryTests().disabled_ports(self.composition)
                with self.clients() as acquire, patch.object(server, "_install_operations_schema"), \
                        patch.object(server, "_secret_provider_composition"), \
                        patch.object(server, "_operations_effect_ports", return_value=ports), \
                        patch.object(server.psycopg, "connect", side_effect=AssertionError("unexpected database IO")):
                    application = server._operations_application(config,
                        principal_authorizer=server._configured_principal_authorizer(config))
                    shared = CpkServerApplicationBoundary(application, verifier)
                    contract = create_cpk_server_composition(config.process_configuration())
                    http = CpkServerHttpProcessBoundary(contract, shared)
                    mcp = CpkServerMcpProcessBoundary(contract, shared)
                    acquire.assert_not_called()
                    self.assertEqual(self.http(http).status, 200)
                    self.assertEqual(self.mcp(mcp).status, 200)
                    self.assertEqual(acquire.call_count, 2)
                    denied = http.handle(method="GET", path="/workspaces/workspace-a/graphs/current",
                        headers={"Authorization": "Bearer caller-token"}, body=b"")
                    self.assertEqual(denied.status, 403)
                    self.assertEqual(acquire.call_count, 2)
