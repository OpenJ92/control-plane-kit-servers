"""Process support policy admission; no image qualification or managed effects."""
from contextlib import ExitStack, redirect_stdout
from dataclasses import FrozenInstanceError, replace
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_core.products import ProductReference
from control_plane_kit_operations import EffectAttemptStartService
from control_plane_kit_operations.health_signing_authority import HealthSigningAuthorityReloadService
from cpk_http_host_fixtures import fixture
from health_receiver_join_fixtures import document, gateway_self_world
from test_http_mcp_boundaries import DeterministicVerifier


PROFILE = "cpk-managed-health-source-support.v1"
MODULE = "control_plane_kit_servers_cpk_server.managed_health_support"


class ManagedHealthSupportTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self.clear_modules)
        self.control = fixture()
        cpk = importlib.import_module("control_plane_kit_servers_cpk_server.control_configuration")
        hello = importlib.import_module("control_plane_kit_servers_hello_server.configuration")
        config = self.control.config
        hello_config = hello.HelloControlConfiguration(
            target=replace(config.target, node_id=replace(config.target.node_id, value="hello-a"),
                           provider_socket_name=replace(config.target.provider_socket_name, value="internal")),
            runtime_id=config.runtime_id, declaration=hello.hello_control_declaration(),
            surface_issuer=config.surface_issuer, surface_keys=config.surface_keys,
            health_issuer=config.health_issuer, health_keys=config.health_keys)
        self.documents = {
            "cpk-workload": document("cpk-support-source", cpk.cpk_source_runtime_contract(
                cpk.CpkSourceVariant.CPK, cpk.cpk_control_configuration_artifact(config))),
            "hello-workload": document("hello-support-source", hello.hello_source_runtime_contract(
                hello.hello_control_configuration_artifact(hello_config))),
            "gateway": gateway_self_world().document,
        }
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "actual startup support loader is missing")
        self.api = importlib.import_module(MODULE)
        self.server = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "support.json"

    @staticmethod
    def clear_modules():
        for name in tuple(sys.modules):
            if any(name == root or name.startswith(root + ".") for root in (
                    "control_plane_kit_servers_cpk_server", "control_plane_kit_servers_cpk_local_gateway",
                    "control_plane_kit_servers_hello_server")):
                sys.modules.pop(name, None)

    def payload(self):
        return {"profile": PROFILE, "products": [
            {"role": role, "document": json.loads(doc.content)} for role, doc in self.documents.items()]}

    def raw(self):
        return json.dumps(self.payload()).encode()

    def write(self, raw=None):
        if self.path.exists():
            self.path.chmod(0o644)
        self.path.write_bytes(self.raw() if raw is None else raw)
        self.path.chmod(0o444)
        return str(self.path)

    def environ(self, *, include_file=True):
        return {"CPK_SERVER_MODE": "execution-capable", "CPK_PORT": "8080",
            "CPK_RUNTIME_INTERPRETERS": "none",
            **{f"CPK_{store}_DATABASE_URL": "postgres://fixture:fixture@database.invalid/db"
               for store in ("WORKPLACE", "ACTIVITY_HISTORY", "OBSERVER_STATE", "GRAPH_TOPOLOGY")},
            **({"CPK_MANAGED_HEALTH_SUPPORT_FILE": str(self.path)} if include_file else {})}

    def refuse(self, action):
        with self.assertRaises(self.api.ManagedHealthSupportError) as caught:
            action()
        self.assertEqual(str(caught.exception), "managed health support is invalid")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(vars(caught.exception), {})

    def assert_registry(self, registry):
        self.assertEqual(len(registry.bindings), 4)
        for role, doc in self.documents.items():
            purposes = (core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,)
            if role == "gateway":
                purposes += (core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT,)
            for purpose in purposes:
                binding = registry.binding_for(ProductReference.from_document(doc), purpose)
                self.assertEqual(binding.product_reference, ProductReference.from_document(doc))

    def test_closed_canonical_snapshot_binds_all_roles_and_is_immutable(self):
        support = self.api.decode_managed_health_support(self.raw())
        self.assertEqual({entry.role: entry.document for entry in support.products}, self.documents)
        self.assert_registry(support.receiver_decoders)
        self.assertIsNone(support.native_reader_document)
        with self.assertRaises(FrozenInstanceError):
            support.products = ()
        for value in (support, *support.products):
            self.assertNotIn("BEGIN PUBLIC KEY", repr(value))
        self.assertTrue(all(doc.product.runtime_contract.verification.checks for doc in self.documents.values()))

    def test_unknown_duplicate_conflicting_and_malformed_documents_refuse(self):
        original = self.payload()
        entry = original["products"][0]
        cases = [None, [], {**original, "extra": True}, {**original, "profile": "unknown"},
            {**original, "products": {}}, {**original, "products": [entry] * 17},
            {**original, "products": [entry, entry]},
            {**original, "products": [entry, {**entry, "role": "hello-workload"}]},
            {**original, "products": [{**entry, "role": "arbitrary.import"}]},
            {**original, "products": [{**entry, "command": ["unapproved"]}]},
            {**original, "products": [{**entry, "document": "https://example.invalid/product"}]},
            {**original, "products": [{"role": "hello-workload", "document": entry["document"]}]}]
        absent = document("no-slots", replace(self.documents["cpk-workload"].product.runtime_contract,
                                             configuration_artifacts=()))
        cases.append({**original, "products": [{"role": "cpk-workload", "document": json.loads(absent.content)}]})
        for index, value in enumerate(cases):
            with self.subTest(case=index):
                self.refuse(lambda: self.api.decode_managed_health_support(json.dumps(value).encode()))
        for raw in (b"", b"\xff", b"not-json", b" " * (1048576 + 1),
                    b'{"profile":"duplicate","profile":"' + PROFILE.encode() + b'","products":[]}'):
            self.refuse(lambda: self.api.decode_managed_health_support(raw))

    def test_native_reader_binding_is_exact_and_singular_without_image_claim(self):
        # A policy document pins an independently supplied reference; parsing
        # does not inspect image bytes or qualify this never-executed fixture.
        native = document("native-policy-input", core.ProductRuntimeContract())
        entry = {"role": "cloudflared-native-reader-v1", "document": json.loads(native.content)}
        support = self.api.decode_managed_health_support(json.dumps(
            {"profile": PROFILE, "products": [entry]}).encode())
        self.assertEqual(support.native_reader_document, native)
        self.assertEqual(support.receiver_decoders.bindings, ())
        other = document("other-native-policy", native.product.runtime_contract)
        self.refuse(lambda: self.api.decode_managed_health_support(json.dumps(
            {"profile": PROFILE, "products": [entry, {**entry, "document": json.loads(other.content)}]}).encode()))

    def test_opened_file_integrity_and_bounds_and_absence(self):
        empty = self.api.read_managed_health_support(None)
        self.assertEqual(empty.products, ())
        self.assertEqual(empty.receiver_decoders.bindings, ())
        self.write()
        self.assert_registry(self.api.read_managed_health_support(str(self.path)).receiver_decoders)
        for path in ("relative.json", "", str(self.path.parent), str(self.path) + ".missing"):
            self.refuse(lambda: self.api.read_managed_health_support(path))
        link = self.path.parent / "link.json"
        link.symlink_to(self.path)
        self.refuse(lambda: self.api.read_managed_health_support(str(link)))
        self.path.chmod(0o644)
        self.refuse(lambda: self.api.read_managed_health_support(str(self.path)))
        self.write(b" " * (1048576 + 1))
        self.refuse(lambda: self.api.read_managed_health_support(str(self.path)))
        self.write()
        info = self.path.stat()
        foreign = SimpleNamespace(st_mode=info.st_mode, st_size=info.st_size, st_uid=65533)
        with patch.object(self.api.os, "fstat", return_value=foreign), patch.object(self.api.os, "geteuid", return_value=10001):
            self.refuse(lambda: self.api.read_managed_health_support(str(self.path)))

    def test_actual_main_shares_startup_snapshot_with_both_real_consumers(self):
        self.write()
        captured = []
        original = self.server.ExecutionCoordinator
        def coordinator(*args, **kwargs):
            result = original(*args, **kwargs)
            captured.append(result)
            return result
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, self.environ(), clear=True))
            stack.enter_context(patch.object(self.server, "_credential_verifier", return_value=DeterministicVerifier()))
            stack.enter_context(patch.object(self.server, "read_cpk_control_configuration", return_value=self.control.config))
            stack.enter_context(patch.object(self.server, "_install_operations_schema", side_effect=lambda _: self.write(b"changed-after-read")))
            stack.enter_context(patch.object(self.server.psycopg, "connect", side_effect=AssertionError("unexpected database access")))
            stack.enter_context(patch.object(self.server, "ExecutionCoordinator", side_effect=coordinator))
            listen = stack.enter_context(patch.object(self.server.uvicorn, "run"))
            output = stack.enter_context(redirect_stdout(io.StringIO()))
            self.assertEqual(self.server.main(), 0)
        listen.assert_called_once()
        self.assertEqual(len(captured), 1)
        execution = captured[0]
        self.assertIsInstance(execution._start_service, EffectAttemptStartService)
        self.assertIsInstance(execution._health_signing_authority, HealthSigningAuthorityReloadService)
        for owner in (execution._start_service, execution._health_signing_authority):
            self.assert_registry(owner._health_receiver_decoders)
        self.assertEqual(execution._start_service._health_receiver_decoders,
                         execution._health_signing_authority._health_receiver_decoders)
        self.assertIsNone(execution._managed_health)
        self.assertEqual(self.path.read_bytes(), b"changed-after-read")
        self.assertNotIn("BEGIN PUBLIC KEY", output.getvalue())

    def test_actual_main_invalid_present_file_stops_before_schema_or_listener(self):
        self.write(b"private-candidate-marker")
        with patch.dict(os.environ, self.environ(), clear=True), \
             patch.object(self.server, "_credential_verifier", return_value=DeterministicVerifier()), \
             patch.object(self.server, "read_cpk_control_configuration", return_value=self.control.config), \
             patch.object(self.server, "_install_operations_schema") as schema, \
             patch.object(self.server, "ExecutionCoordinator") as coordinator, \
             patch.object(self.server.uvicorn, "run") as listen, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.server.main(), 2)
        schema.assert_not_called()
        coordinator.assert_not_called()
        listen.assert_not_called()
        self.assertIn("managed health support is invalid", output.getvalue())
        self.assertNotIn("private-candidate-marker", output.getvalue())

    def test_absent_startup_support_retains_empty_consumers_and_no_managed_port(self):
        config = self.server.CpkServerBootstrapConfiguration.from_environment(self.environ(include_file=False))
        with patch.object(self.server, "_install_operations_schema"), \
             patch.object(self.server.psycopg, "connect", side_effect=AssertionError("unexpected database access")):
            application = self.server._operations_application(config)
        execution = application.services[core.ControlPlaneServiceRole.EXECUTION]._service
        self.assertEqual(execution._start_service._health_receiver_decoders.bindings, ())
        self.assertEqual(execution._health_signing_authority._health_receiver_decoders.bindings, ())
        self.assertIsNone(execution._managed_health)
