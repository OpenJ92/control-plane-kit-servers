"""Finite #221 setup/action laws; no user credentials or external effects."""
import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

import control_plane_kit_core as core
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from control_plane_kit_interpreters.secret_provider import canonical_provider_secret_id
from control_plane_kit_core.secrets import SecretReference


def api(test):
    try:
        return importlib.import_module("control_plane_kit_servers_cpk_server.gateway_diagnostic_actions")
    except ModuleNotFoundError as error:
        if error.name != "control_plane_kit_servers_cpk_server.gateway_diagnostic_actions": raise
        test.fail("missing finite diagnostic setup/action composition")


HOST = "cpk-bootstrap-grandparent.openj92.dev"
ORIGIN = "http://retained-origin.internal:8080"
TUNNEL = "d77c7e6b-9a41-4d35-b20c-aed03e0a21ea"


class RouteProvider:
    def __init__(self):
        self.config = {"ingress": [{"hostname": HOST, "service": ORIGIN},
                                  {"service": "http_status:404"}], "warp-routing": {"enabled": False}}
        self.calls = []
        self.connections = []
        self.lose_put = False
        self.drift_after_put = False
        self.bad_put_response = False

    def get_config(self):
        self.calls.append("get-config")
        return copy.deepcopy(self.config)

    def get_connections(self):
        self.calls.append("get-connections")
        return list(self.connections)

    def put_config(self, value):
        self.calls.append(("put-config", copy.deepcopy(value)))
        self.config = copy.deepcopy(value)
        if self.drift_after_put:
            self.config["ingress"][0]["service"] = "http://concurrent-writer.internal:9000"
        if self.lose_put: raise TimeoutError("private-provider-body")
        if self.bad_put_response: return {"malformed": True}
        return copy.deepcopy(value)


class GatewayDiagnosticActionTests(unittest.TestCase):
    def test_generated_keys_use_actual_selected_secrets_provider_and_scoped_credentials(self):
        module = api(self)
        from fastapi.testclient import TestClient
        from control_plane_kit_secrets.api import create_app
        from control_plane_kit_secrets.bootstrap import load_provider_credentials
        from control_plane_kit_secrets.control import decode_secrets_control_configuration
        from control_plane_kit_secrets.crypto import load_master_key_file
        from control_plane_kit_secrets.custody import admit_provider_custody
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fresh"
            module.prepare_private_material(root)
            store, audit = admit_provider_custody(root / "provider.sqlite3",
                master_key=load_master_key_file(root / "master.key", version="fixture"),
                provider_id="cpk221-self-health-r1")
            credentials = load_provider_credentials({"CPK_SECRETS_CREDENTIALS_FILE": str(root / "provider-credentials.json")})
            control = decode_secrets_control_configuration((root / "secrets-control.json").read_bytes())
            with TestClient(create_app(control=control, provider_id="cpk221-self-health-r1",
                    initialize_provider=lambda: (store, audit, credentials))) as provider:
                calls = []
                def handle(request):
                    calls.append(request.url.path)
                    response = provider.request(request.method, request.url.raw_path.decode(),
                        headers=dict(request.headers), content=request.content)
                    return httpx.Response(response.status_code, headers=response.headers, content=response.content)
                results = module.generate_health_keys(root, transport=httpx.MockTransport(handle))
            self.assertEqual(len(results), 2)
            self.assertEqual(calls, [action["path"] for action in module.generation_actions()])
            self.assertEqual(len({result["fingerprint_sha256"] for result in results}), 2)
            self.assertNotIn("PRIVATE KEY", json.dumps(results))

    def test_two_provider_generations_are_single_send_and_partial_failure_is_retained(self):
        module = api(self)
        for fail_second in (False, True):
            with self.subTest(fail_second=fail_second), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "fresh"
                module.prepare_private_material(root)
                actions, calls = module.generation_actions(), []

                def handle(request):
                    index = len(calls)
                    calls.append(request)
                    self.assertEqual(request.method, "POST")
                    self.assertEqual(request.headers["authorization"],
                        "Bearer " + (root / "provider-generate.token").read_text().strip())
                    self.assertEqual(request.url.path, actions[index]["path"])
                    self.assertEqual(json.loads(request.content), actions[index]["body"])
                    if fail_second and index == 1: raise httpx.ReadTimeout("provider-private", request=request)
                    return httpx.Response(200, json=generated(actions[index]))

                transport = httpx.MockTransport(handle)
                if fail_second:
                    with self.assertRaises(module.SetupHold): module.generate_health_keys(root, transport=transport)
                else:
                    values = module.generate_health_keys(root, transport=transport)
                    self.assertEqual(len(values), 2)
                self.assertEqual(len(calls), 2)
                receipt = json.loads((root / "generation-receipt.json").read_text())
                self.assertEqual(len(receipt["completed"]), 1 if fail_second else 2)
                self.assertEqual(receipt["pending"], "workload" if fail_second else None)
                with self.assertRaises(module.SetupHold): module.generate_health_keys(root, transport=transport)
                self.assertEqual(len(calls), 2)
                self.assertNotIn("provider-private", json.dumps(receipt))

    def test_setup_authentication_precedes_schema_or_operations_writes(self):
        module = api(self)
        from control_plane_kit_servers_cpk_server.authentication import authenticate_bearer_credential
        from control_plane_kit_core.policies import PolicyScope
        for presented in ("unrecognized", "runner"):
            with self.subTest(presented=presented), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "fresh"
                module.prepare_private_material(root)
                actions = module.generation_actions()
                module.generate_health_keys(root, transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=generated(next(
                        action for action in actions if action["path"] == request.url.path)))))
                # Presenting another token never changes independently protected bindings.
                token = "unrecognized-credential" if presented == "unrecognized" else (root / "runner-operator.token").read_text()
                (root / "setup-operator.token").write_text(token)
                called, authenticated = [], []
                def authenticate(headers, verifier):
                    principal = authenticate_bearer_credential(headers, verifier)
                    authenticated.append(principal.command_context("cpk221-self-health-r1"))
                    return principal
                with patch.object(module, "authenticate_bearer_credential", side_effect=authenticate):
                    with self.assertRaises(module.SetupHold):
                        module.initialize_operations(root, schema_initializer=lambda: called.append("schema"),
                            uow_factory=lambda: called.append("uow"))
                self.assertEqual(called, [])
                self.assertEqual(len(authenticated), 0 if presented == "unrecognized" else 1)
                if authenticated:
                    self.assertEqual(set(authenticated[0].granted_scopes), {PolicyScope.SECRET_PROVIDER_USE})

    def test_operations_partial_commit_receipt_stops_reentry_and_downstream_calls(self):
        module = api(self)
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fresh"
            module.prepare_private_material(root)
            actions = module.generation_actions()
            module.generate_health_keys(root, transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=generated(next(
                    action for action in actions if action["path"] == request.url.path)))))
            called = []
            with patch.object(module, "WorkspaceCommandService") as workspaces, \
                 patch.object(module, "SecretProviderRegistrationService") as providers, \
                 patch.object(module, "DelegationSigningKeyRegistrationService") as keys:
                workspaces.return_value.create.return_value = SimpleNamespace(
                    replayed=False, current_graph=SimpleNamespace(graph_id="owner-returned-graph"))
                providers.return_value.register_provider.return_value = SimpleNamespace(registration_id="sprov_" + "a" * 64)
                providers.return_value.register_reference.return_value = SimpleNamespace(registration_id="sref_" + "b" * 64)
                keys.return_value.register.side_effect = RuntimeError("private-database-canary")
                with self.assertRaises(module.SetupHold) as raised:
                    module.initialize_operations(root, schema_initializer=lambda: called.append("schema"), uow_factory=lambda: None)
                receipt = json.loads((root / "operations-receipt.json").read_text())
                self.assertNotEqual(receipt["status"], "complete")
                self.assertEqual(receipt["graph_id"], "owner-returned-graph")
                self.assertEqual(receipt["provider_registration_id"], "sprov_" + "a" * 64)
                self.assertEqual(receipt["keys"][0]["reference_registration_id"], "sref_" + "b" * 64)
                self.assertEqual(receipt["pending"], "register-transit-key")
                self.assertNotIn("private-database-canary", json.dumps(receipt) + repr(raised.exception))
                keys.return_value.activate.assert_not_called()
                before = (list(workspaces.mock_calls), list(providers.mock_calls), list(keys.mock_calls))
                with self.assertRaises(module.SetupHold):
                    module.initialize_operations(root, schema_initializer=lambda: called.append("schema"), uow_factory=lambda: None)
                self.assertEqual(called, ["schema"])
                self.assertEqual(before, (list(workspaces.mock_calls), list(providers.mock_calls), list(keys.mock_calls)))

    def test_setup_calls_existing_services_with_authenticated_identity_and_returned_ids(self):
        module = api(self)
        from types import SimpleNamespace
        from control_plane_kit_core.policies import PolicyScope
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fresh"
            module.prepare_private_material(root)
            actions = module.generation_actions()
            module.generate_health_keys(root, transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=generated(next(
                    action for action in actions if action["path"] == request.url.path)))))
            created = []
            # These spies exercise adapter wiring; provider/API and Operations laws
            # remain owned by their actual implementations, not these return stubs.
            with patch.object(module, "WorkspaceCommandService") as workspaces, \
                 patch.object(module, "SecretProviderRegistrationService") as providers, \
                 patch.object(module, "DelegationSigningKeyRegistrationService") as keys:
                workspaces.return_value.create.return_value = SimpleNamespace(
                    replayed=False, current_graph=SimpleNamespace(graph_id="owner-returned-graph"))
                providers.return_value.register_provider.return_value = SimpleNamespace(registration_id="sprov_" + "a" * 64)
                providers.return_value.register_reference.side_effect = [SimpleNamespace(registration_id="sref_" + value * 64) for value in "bc"]
                keys.return_value.register.side_effect = lambda command: SimpleNamespace(
                    registration_id="dkey_" + command.public_key.key_id, public_key=command.public_key)
                keys.return_value.activate.side_effect = lambda command: SimpleNamespace(
                    registration_id="dkey_" + command.key_id, public_key=next(
                        call.args[0].public_key for call in keys.return_value.register.call_args_list
                        if call.args[0].public_key.key_id == command.key_id))
                module.initialize_operations(root, schema_initializer=lambda: created.append("schema"), uow_factory=lambda: None)
                self.assertEqual(created, ["schema"])
                command = workspaces.return_value.create.call_args.args[0]
                self.assertEqual(command.workspace_id, "cpk221-self-health-r1")
                self.assertIn("cpk221-setup-operator", command.actor_id)
                self.assertEqual(providers.return_value.register_reference.call_count, 2)
                for call in providers.return_value.register_reference.call_args_list:
                    self.assertEqual(call.args[0].provider_registration_id, "sprov_" + "a" * 64)
                    self.assertEqual(len(call.args[0].allowed_intents), 1)
                self.assertEqual(keys.return_value.register.call_count, 2)
                self.assertEqual(keys.return_value.activate.call_count, 2)
                for call in keys.return_value.register.call_args_list:
                    self.assertIn(PolicyScope.DELEGATION_KEY_REGISTER, call.args[0].actor_scopes)
                    self.assertNotIn(PolicyScope.SECRET_PROVIDER_USE, call.args[0].actor_scopes)
            receipt = json.loads((root / "operations-receipt.json").read_text())
            self.assertEqual(receipt["graph_id"], "owner-returned-graph")
            self.assertEqual(receipt["provider_registration_id"], "sprov_" + "a" * 64)
            with self.assertRaises(module.SetupHold): module.initialize_operations(root)

    def test_generated_public_artifacts_and_packet_pass_existing_diagnostic_decoder(self):
        module = api(self)
        from control_plane_kit_servers_cpk_server._gateway_diagnostic_input import prepare_packet
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fresh"
            module.prepare_private_material(root)
            actions = module.generation_actions()
            module.generate_health_keys(root, transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=generated(next(
                    action for action in actions if action["path"] == request.url.path)))))
            # Explicit synthetic owner-returned metadata for pure artifact assembly;
            # not live admission or an implementation of Operations stores.
            operations = {"status": "complete", "graph_id": "fixture-owner-graph",
                "provider_registration_id": "sprov_" + "a" * 64,
                "keys": [{"registration_id": "dkey_" + marker * 64,
                          "reference_registration_id": "sref_" + marker * 64} for marker in "bc"]}
            (root / "operations-receipt.json").write_text(json.dumps(operations))
            (root / "operations-receipt.json").chmod(0o600)
            module.build_artifacts(root, gateway_image_digest="sha256:" + "a" * 64,
                runtime_id="fixture-runtime", private_hostname="fixture-gateway")
            approval = dict(controller_image_digest="sha256:" + "b" * 64,
                resource_plan="approved-resource-plan", expires_at=2000000299)
            with self.assertRaises(module.SetupHold): module.seal_approved_packet(root, approval, now=2000000000)
            for name in ("packet.json", "runner-approval.json", "runner-principals.json", "runner-bootstrap.json"):
                self.assertFalse((root / name).exists())
            approval["expires_at"] = 2000000600
            raw = module.seal_approved_packet(root, approval, now=2000000000)
            artifacts = {name: (root / "artifacts" / (name + ".json")).read_bytes()
                         for name in ("control", "transit", "targets", "product")}
            result = prepare_packet(raw, artifacts)
            self.assertEqual(result.plan()["status"], "offline-plan")
            from control_plane_kit_servers_cpk_server._gateway_diagnostic_bootstrap import read_authority
            from control_plane_kit_servers_cpk_server.gateway_self_health_diagnostic import _approval
            authority = read_authority(root / "runner-bootstrap.json")
            principal = authority.verifier.authenticate(authority.credential)
            admitted = _approval(result, authority, principal.command_context(module.WORKSPACE), lambda: 2000000001)
            self.assertEqual(admitted["expires_at"], 2000000300)
            self.assertNotIn("PRIVATE KEY", raw.decode())
            with self.assertRaises(module.SetupHold):
                module.seal_packet(root, controller_image_digest="sha256:" + "b" * 64,
                    resource_plan="approved-resource-plan", now=2000000001)

    def test_route_change_preserves_complete_config_and_restores_guarded_snapshot(self):
        module = api(self)
        provider = RouteProvider()
        original = copy.deepcopy(provider.config)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = module.change_route(root, ORIGIN, provider)
            self.assertEqual(changed["status"], "route-updated")
            expected = copy.deepcopy(original)
            expected["ingress"][0]["service"] = "http://retained-origin.internal:8000"
            self.assertEqual(provider.config, expected)
            self.assertEqual(provider.calls, ["get-config", "get-connections", ("put-config", expected), "get-config"])
            snapshot = root / "route-original.json"
            self.assertEqual(json.loads(snapshot.read_text()), original)
            self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
            restored = module.restore_route(root, provider)
            self.assertEqual(restored["status"], "route-restored")
            self.assertEqual(provider.config, original)
            self.assertEqual(len([value for value in provider.calls if isinstance(value, tuple)]), 2)

    def test_route_drift_connections_or_existing_receipt_refuse_before_put(self):
        module = api(self)
        for fault in ("origin", "connections", "existing"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root, provider = Path(directory), RouteProvider()
                if fault == "origin": provider.config["ingress"][0]["service"] = "http://other.internal:8080"
                elif fault == "connections": provider.connections = [{"id": "existing"}]
                else: (root / "route-action.json").write_text("{}")
                with self.assertRaises(module.SetupHold): module.change_route(root, ORIGIN, provider)
                self.assertFalse(any(isinstance(value, tuple) for value in provider.calls))

    def test_lost_route_put_retains_pending_evidence_and_never_retries(self):
        module = api(self)
        provider = RouteProvider()
        provider.lose_put = True
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(module.SetupHold) as raised:
                module.change_route(root, ORIGIN, provider)
            receipt = json.loads((root / "route-action.json").read_text())
            self.assertEqual(receipt["status"], "pending-update")
            self.assertTrue((root / "route-original.json").exists())
            with self.assertRaises(module.SetupHold): module.change_route(root, ORIGIN, provider)
            self.assertEqual(len([value for value in provider.calls if isinstance(value, tuple)]), 1)
            self.assertNotIn("private-provider-body", repr(raised.exception))

    def test_restore_never_overwrites_a_concurrent_change(self):
        module = api(self)
        with tempfile.TemporaryDirectory() as directory:
            root, provider = Path(directory), RouteProvider()
            module.change_route(root, ORIGIN, provider)
            provider.config["ingress"][0]["service"] = "http://other-writer.internal:9000"
            with self.assertRaises(module.SetupHold): module.restore_route(root, provider)
            self.assertEqual(len([value for value in provider.calls if isinstance(value, tuple)]), 1)
            self.assertEqual(provider.config["ingress"][0]["service"], "http://other-writer.internal:9000")

    def test_restore_connections_uncertain_response_and_verification_hold_without_replay(self):
        module = api(self)
        for fault in ("connections", "lost-put", "post-put-drift"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root, provider = Path(directory), RouteProvider()
                original = copy.deepcopy(provider.config)
                module.change_route(root, ORIGIN, provider)
                if fault == "connections": provider.connections = [{"id": "active"}]
                elif fault == "lost-put": provider.lose_put = True
                else: provider.drift_after_put = True
                with self.assertRaises(module.SetupHold) as raised: module.restore_route(root, provider)
                if fault == "post-put-drift": self.assertEqual(provider.calls[-1], "get-config")
                self.assertNotIn("private-provider-body", repr(raised.exception))
                self.assertEqual(json.loads((root / "route-original.json").read_text()), original)
                if fault != "connections":
                    receipt = json.loads((root / "route-restore.json").read_text())
                    self.assertEqual(receipt["status"], "pending-restore")
                    self.assertEqual((root / "route-restore.json").stat().st_mode & 0o777, 0o600)
                    with self.assertRaises(module.SetupHold): module.restore_route(root, provider)
                self.assertEqual(len([value for value in provider.calls if isinstance(value, tuple)]),
                    1 if fault == "connections" else 2)

    def test_update_post_put_drift_cannot_report_success_or_repeat_write(self):
        module = api(self)
        with tempfile.TemporaryDirectory() as directory:
            root, provider = Path(directory), RouteProvider()
            provider.drift_after_put = True
            with self.assertRaises(module.SetupHold): module.change_route(root, ORIGIN, provider)
            self.assertEqual(provider.calls[-1], "get-config")
            self.assertEqual(json.loads((root / "route-action.json").read_text())["status"], "pending-update")
            with self.assertRaises(module.SetupHold): module.change_route(root, ORIGIN, provider)
            self.assertEqual(len([value for value in provider.calls if isinstance(value, tuple)]), 1)

    def test_malformed_put_response_never_reports_success_or_repeats(self):
        module = api(self)
        for phase in ("update", "restore"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root, provider = Path(directory), RouteProvider()
                if phase == "restore": module.change_route(root, ORIGIN, provider)
                provider.bad_put_response = True
                call = lambda: module.change_route(root, ORIGIN, provider) if phase == "update" else module.restore_route(root, provider)
                with self.assertRaises(module.SetupHold): call()
                with self.assertRaises(module.SetupHold): call()
                self.assertEqual(len([value for value in provider.calls if isinstance(value, tuple)]), 1 if phase == "update" else 2)

    def test_real_cloudflare_adapter_limits_paths_methods_bodies_and_validates_put(self):
        module = api(self)
        from control_plane_kit_servers_cpk_server.gateway_ingress_admission import Credentials
        from control_plane_kit_core.secrets import SecretValue
        original = RouteProvider().config
        path = "/client/v4/accounts/account-a/cfd_tunnel/" + TUNNEL
        calls = []
        def handle(request):
            calls.append((request.method, request.url.path))
            self.assertEqual(request.headers["authorization"], "Bearer test-api-token")
            if request.url.path.endswith("/connections"):
                return httpx.Response(200, json={"success": True, "result": []})
            if request.method == "PUT": self.assertEqual(json.loads(request.content), {"config": original})
            return httpx.Response(200, json={"success": True, "result": {"config": original}})
        provider = module.CloudflareRouteProvider(Credentials("account-a", "zone-a", SecretValue("test-api-token")),
            transport=httpx.MockTransport(handle))
        self.assertEqual(provider.get_config(), original)
        self.assertEqual(provider.get_connections(), [])
        self.assertEqual(provider.put_config(original), original)
        self.assertEqual(calls, [("GET", path + "/configurations"), ("GET", path + "/connections"), ("PUT", path + "/configurations")])
        for method, suffix in (("DELETE", "/configurations"), ("GET", "/token"), ("PUT", "/connections")):
            with self.assertRaises(module.SetupHold):
                provider.client.transport.request(method, "https://api.cloudflare.com" + path + suffix, headers={})
        self.assertEqual(len(calls), 3)
        malformed = module.CloudflareRouteProvider(Credentials("account-a", "zone-a", SecretValue("test-api-token")),
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"success": True, "result": {"config": {}}})))
        with self.assertRaises(module.SetupHold): malformed.put_config(original)

    def test_cli_requires_independent_protected_unexpired_exact_source_approval(self):
        module = api(self)
        import contextlib
        import io
        from hashlib import sha256
        import time
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approval.json"
            approval = dict(profile="cpk221-approved-setup.v1", source_sha256=sha256(Path(module.__file__).read_bytes()).hexdigest(),
                root="/private/tmp/cpk221-self-health-r1", expires_at=int(time.time()) + 300, phases=["generate"], resource_plan="reviewed-plan",
                controller_image_digest="sha256:" + "a" * 64, gateway_image_digest="sha256:" + "b" * 64,
                runtime_id="runtime-a", ingress_receipt_file="/private/mounted/receipt", cloudflare_credentials_file="/private/mounted/credentials")
            for fault in (None, "source", "expired", "phase", "mode"):
                with self.subTest(fault=fault):
                    value = dict(approval)
                    if fault == "source": value["source_sha256"] = "0" * 64
                    elif fault == "expired": value["expires_at"] = 0
                    elif fault == "phase": value["phases"] = []
                    path.write_text(json.dumps(value))
                    path.chmod(0o644 if fault == "mode" else 0o600)
                    output = io.StringIO()
                    with patch.object(module, "generate_health_keys", return_value=[]) as generate, contextlib.redirect_stdout(output):
                        result = module.main(["generate", "--approval", str(path)])
                    self.assertEqual(result, 0 if fault is None else 2)
                    self.assertEqual(generate.call_count, 1 if fault is None else 0)
                    self.assertLessEqual(len(output.getvalue()), 4096)

    def test_generation_actions_are_the_two_exact_approved_original_requests(self):
        module = api(self)
        actions = module.generation_actions()
        self.assertEqual(len(actions), 2)
        for family, action, purpose, intent in zip(("transit", "workload"), actions,
                (core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT,
                 core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ),
                ("gateway.node-health-read-transit-signing-key", "workload.node-health-read-signing-key"), strict=True):
            self.assertEqual(action["workspace_id"], "cpk221-self-health-r1")
            self.assertEqual(action["reference"], "secret://cpk221-self-health-r1/keys/" + family + "-health")
            self.assertEqual(action["body"], {"purpose": purpose.value, "issuer": "cpk221-" + family,
                "caller_subject": "cpk221-setup-operator", "correlation_id": "cpk221-self-health-r1:generate:" + family,
                "secret_reference": action["reference"]})
            self.assertEqual(action["intent"], intent)
            self.assertEqual(action["path"], "/v1/workspaces/cpk221-self-health-r1/delegation-keys/" +
                canonical_provider_secret_id(SecretReference(action["reference"])) + "/generate")

    def test_provider_response_requires_original_binding_and_public_only_closed_shape(self):
        module = api(self)
        for action in module.generation_actions():
            original = generated(action)
            result = module.validate_generated_key(action, original)
            self.assertIsInstance(result, core.DelegationPublicKey)
            self.assertEqual(result.fingerprint_sha256, original["fingerprint_sha256"])
            for fault in ("workspace_id", "secret_id", "intent", "issuer", "correlation_id", "replayed", "private", "fingerprint_sha256",
                          "secret_reference", "purpose", "label-purpose", "label-issuer", "label-key_id"):
                with self.subTest(fault=fault):
                    payload = copy.deepcopy(original)
                    if fault in ("workspace_id", "secret_id"): payload["metadata"][fault] = "substituted"
                    elif fault == "intent": payload["metadata"]["labels"]["intent"] = "gateway.probe-signing-key"
                    elif fault.startswith("label-"): payload["metadata"]["labels"][fault.removeprefix("label-")] = "substituted"
                    elif fault == "replayed": payload[fault] = True
                    else: payload[fault] = "private-substituted-canary"
                    with self.assertRaises(module.SetupHold) as raised: module.validate_generated_key(action, payload)
                    self.assertNotIn("private-substituted-canary", repr(raised.exception))

    def test_bootstrap_material_is_private_separated_and_public_verifiers_decode(self):
        module = api(self)
        from control_plane_kit_secrets.control import decode_secrets_control_configuration
        from control_plane_kit_secrets.bootstrap import load_provider_credentials
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fresh"
            module.prepare_private_material(root)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            for name in ("master.key", "provider-credentials.json", "provider-generate.token", "provider-resolve.token",
                         "setup-operator.token", "runner-operator.token", "postgres-password", "database.dsn"):
                self.assertEqual((root / name).stat().st_mode & 0o777, 0o600)
            credentials = load_provider_credentials({"CPK_SECRETS_CREDENTIALS_FILE": str(root / "provider-credentials.json")})
            self.assertNotEqual((root / "provider-generate.token").read_bytes(), (root / "provider-resolve.token").read_bytes())
            self.assertEqual(len(credentials), 2)
            for family, action in (("generate", "secret.generate-delegation-key"), ("resolve", "secret.resolve")):
                token = (root / ("provider-" + family + ".token")).read_text().strip()
                credential = next(value for value in credentials if value.token == token)
                self.assertEqual(len(credential.grants), 1)
                grant = credential.grants[0]
                self.assertEqual(grant.action, action)
                self.assertEqual(grant.workspace_id, "cpk221-self-health-r1")
                self.assertEqual(set(grant.intents), {value["intent"] for value in module.generation_actions()})
                self.assertEqual(len(grant.intents), 2)
            control = decode_secrets_control_configuration((root / "secrets-control.json").read_bytes())
            self.assertEqual(control.target.workspace_id.value, "cpk221-self-health-r1")
            public = json.loads((root / "bootstrap-public.json").read_text())
            self.assertEqual(len(public), 3)
            self.assertEqual(len({value["fingerprint"] for value in public}), 3)
            for path in root.iterdir(): self.assertNotIn(b"PRIVATE KEY", path.read_bytes())
            with self.assertRaises(module.SetupHold): module.prepare_private_material(root)


def generated(action):
    private = Ed25519PrivateKey.generate()
    family = "transit" if action["body"]["purpose"] == "gateway-node-health-read-transit" else "workload"
    public = core.DelegationPublicKey("generated-" + family, core.DelegationKeyAlgorithm.ED25519,
        private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())
    body = action["body"]
    return {"outcome": "generated", "secret_reference": action["reference"],
        "metadata": {"workspace_id": action["workspace_id"],
            "secret_id": canonical_provider_secret_id(SecretReference(action["reference"])),
            "version_id": "version-1", "version_number": 1, "status": "active", "algorithm": "AES-256-GCM",
            "key_fingerprint": "a" * 64, "key_version": "diagnostic", "created_at": "2026-09-23T00:00:00Z", "revoked_at": None,
            "labels": {"intent": action["intent"], "purpose": body["purpose"], "issuer": body["issuer"], "key_id": public.key_id}},
        "purpose": body["purpose"], "issuer": body["issuer"], "correlation_id": body["correlation_id"],
        "replayed": False, "key_id": public.key_id, "algorithm": "ed25519", "public_key_pem": public.public_key_pem,
        "fingerprint_sha256": public.fingerprint_sha256}
