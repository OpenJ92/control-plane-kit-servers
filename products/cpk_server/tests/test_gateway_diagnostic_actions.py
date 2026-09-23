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

    def get_config(self):
        self.calls.append("get-config")
        return copy.deepcopy(self.config)

    def get_connections(self):
        self.calls.append("get-connections")
        return list(self.connections)

    def put_config(self, value):
        self.calls.append(("put-config", copy.deepcopy(value)))
        self.config = copy.deepcopy(value)
        if self.lose_put: raise TimeoutError("private-provider-body")
        return copy.deepcopy(self.config)


class GatewayDiagnosticActionTests(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fresh"
            module.prepare_private_material(root)
            # Presenting another token never changes independently protected bindings.
            (root / "setup-operator.token").write_text("unrecognized-credential")
            called = []
            with self.assertRaises(module.SetupHold):
                module.initialize_operations(root, schema_initializer=lambda: called.append("schema"),
                    uow_factory=lambda: called.append("uow"))
            self.assertEqual(called, [])

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
            module.build_artifacts(root, gateway_image_digest="sha256:" + "a" * 64,
                runtime_id="fixture-runtime", private_hostname="fixture-gateway")
            raw = module.seal_packet(root, controller_image_digest="sha256:" + "b" * 64,
                resource_plan="approved-resource-plan", now=2000000000)
            artifacts = {name: (root / "artifacts" / (name + ".json")).read_bytes()
                         for name in ("control", "transit", "targets", "product")}
            result = prepare_packet(raw, artifacts)
            self.assertEqual(result.plan()["status"], "offline-plan")
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
            for fault in ("workspace_id", "secret_id", "intent", "issuer", "correlation_id", "replayed", "private", "fingerprint_sha256"):
                with self.subTest(fault=fault):
                    payload = copy.deepcopy(original)
                    if fault in ("workspace_id", "secret_id"): payload["metadata"][fault] = "substituted"
                    elif fault == "intent": payload["metadata"]["labels"]["intent"] = "gateway.probe-signing-key"
                    elif fault == "replayed": payload[fault] = True
                    else: payload[fault] = "private-substituted-canary"
                    with self.assertRaises(module.SetupHold) as raised: module.validate_generated_key(action, payload)
                    self.assertNotIn("private-substituted-canary", repr(raised.exception))

    def test_bootstrap_material_is_private_separated_and_public_verifiers_decode(self):
        module = api(self)
        from control_plane_kit_secrets.control import decode_secrets_control_configuration
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fresh"
            module.prepare_private_material(root)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            for name in ("master.key", "provider-credentials.json", "provider-generate.token", "provider-resolve.token",
                         "setup-operator.token", "runner-operator.token", "postgres-password", "database.dsn"):
                self.assertEqual((root / name).stat().st_mode & 0o777, 0o600)
            credentials = json.loads((root / "provider-credentials.json").read_text())
            self.assertNotEqual((root / "provider-generate.token").read_bytes(), (root / "provider-resolve.token").read_bytes())
            self.assertIn("secret.generate-delegation-key", json.dumps(credentials))
            self.assertIn("secret.resolve", json.dumps(credentials))
            control = decode_secrets_control_configuration((root / "secrets-control.json").read_bytes())
            self.assertEqual(control.target.workspace_id.value, "cpk221-self-health-r1")
            public = json.loads((root / "bootstrap-public.json").read_text())
            self.assertEqual(len(public), 3)
            self.assertEqual(len({value["fingerprint"] for value in public}), 3)
            for path in root.iterdir(): self.assertNotIn(b"PRIVATE KEY", path.read_bytes())
            with self.assertRaises(module.SetupHold): module.prepare_private_material(root)


def generated(action):
    private = Ed25519PrivateKey.generate()
    public = core.DelegationPublicKey("generated-health-key", core.DelegationKeyAlgorithm.ED25519,
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
