"""Ordinary listener composition; database/provider/listener are external doubles.

No deployment, current permission, installed daemon or SQL result is asserted.
Selected only by the existing exact-source owning composition gate.
"""
from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_core.products import ProductReference, ProductReferenceCodec
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_servers_cpk_server import server
from control_plane_kit_servers_cpk_server import managed_verification_configuration as reader
from http_sample_installation_assembly import assemble
from cpk_http_host_fixtures import fixture as receiving_fixture
from test_secret_provider_bootstrap import _provider_environment

KEY = "CPK_MANAGED_VERIFICATION_CONFIGURATION_FILE"


class ManagedVerificationStartupTests(unittest.TestCase):
    def setUp(self):
        expected = os.environ.get("CPK_STARTUP_SOURCE_ROOT")
        if expected is not None:
            self.assertTrue(Path(server.__file__).resolve().is_relative_to(Path(expected)))
            self.assertTrue(Path(reader.__file__).resolve().is_relative_to(Path(expected)))
            for name, root in (("control_plane_kit_core", "/reviewed-http-sample/core/src"),
                    ("control_plane_kit_operations", "/reviewed-http-sample/operations/src"),
                    ("control_plane_kit_interpreters", "/reviewed-http-sample/interpreters/src")):
                self.assertTrue(Path(importlib.import_module(name).__file__).resolve().is_relative_to(root))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        custody = self.root / "commissioning"
        custody.mkdir(mode=0o700)
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            material, original, _, graph, gateway, _ = assemble(commissioning_directory=custody)
        finally:
            os.chdir(previous)
        node = graph.node(original.postgres_node_id)
        self.postgres = next(document for document in material.product_documents
            if ProductReference.from_document(document).descriptor_sha256.value == node.metadata["product_descriptor_digest"])
        self.gateway = gateway
        identity = server._static_operator_identity().descriptor()
        authority = dict(schema="cpk-server.workspace-authority.v1", installation_id="sender-startup",
            administrators=[identity], known_identities=[identity], capabilities=["source-docker"])
        health = dict(schema="cpk-server.managed-health.v2",
            docker=dict(socket_path="/var/run/source-not-opened.sock", request_timeout=5.0),
            capability_ids=["source-docker"], gateway_documents=[gateway.content.decode()],
            native_product_document=original.management.connector_product.content.decode())
        for name, value in (("authority", authority), ("health", health)):
            (self.root / (name + ".json")).write_text(json.dumps(value))
        self.path = self.root / "sender.json"
        self.document = dict(schema="cpk-server.managed-verification.v1",
            gateway_product=ProductReferenceCodec().encode(ProductReference.from_document(gateway)),
            postgres_product_document=self.postgres.content.decode())
        self.path.write_text(json.dumps(self.document))
        self.values = {**_provider_environment(self.root / "never-read-provider.token"),
            "CPK_WORKSPACE_AUTHORITY": "dynamic-v1",
            "CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE": str(self.root / "authority.json"),
            "CPK_MANAGED_HEALTH": "docker-unix-v2",
            "CPK_MANAGED_HEALTH_CONFIGURATION_FILE": str(self.root / "health.json"),
            "CPK_CONTROL_AUTH_VERIFIER": "static-development",
            "CPK_CONTROL_AUTH_STATIC_CREDENTIAL": "synthetic-startup-only", KEY: str(self.path)}

    def test_exact_variant_selects_one_support_and_declared_gateway_socket(self):
        config = server.CpkServerBootstrapConfiguration.from_environment(self.values)
        support = config.managed_verification_support
        self.assertIs(config.http_sample_support, support.http_samples)
        self.assertEqual(support.http_samples.gateway_binding.product, ProductReference.from_document(self.gateway))
        self.assertEqual(support.http_samples.transit_provider_socket_name,
            self.gateway.product.runtime_contract.gateway_transit.provider_socket_name)
        observer, = support.postgres_observers
        self.assertEqual(observer.product, ProductReference.from_document(self.postgres))
        self.assertEqual(observer.image, self.postgres.product.image)
        delivery, = self.postgres.product.runtime_contract.secret_deliveries
        self.assertEqual((observer.password_path, observer.password_environment_name),
            (delivery.target_path, delivery.path_binding.environment_name))

    def test_closed_or_crossed_public_configuration_refuses(self):
        base = server.CpkServerBootstrapConfiguration.from_environment({key:value for key,value in self.values.items() if key != KEY})
        foreign = ProductReferenceCodec().encode(ProductReference.from_document(self.postgres))
        documents = [self.document | dict(gateway_product=foreign), self.document | dict(extra="refused"),
            self.document | dict(postgres_product_document=self.gateway.content.decode())]
        for value in documents:
            with self.subTest(keys=tuple(value)), self.assertRaises(ValueError):
                reader.decode_managed_verification_configuration(json.dumps(value).encode(), base)
        raw = json.dumps(self.document).replace('"schema":', '"schema":"duplicate","schema":', 1).encode()
        with self.assertRaises(ValueError):
            reader.decode_managed_verification_configuration(raw, base)
        for changed in (replace(base, workspace_authority=None), replace(base, managed_health_process=None)):
            with self.assertRaises(ValueError):
                reader.decode_managed_verification_configuration(json.dumps(self.document).encode(), changed)

    def test_absent_opt_in_preserves_receiver_configuration(self):
        values = {key:value for key,value in self.values.items() if key != KEY}
        with patch.dict("sys.modules", {reader.__name__: None}):
            config = server.CpkServerBootstrapConfiguration.from_environment(values)
        self.assertIsNone(config.http_sample_support)
        self.assertIsNone(config.managed_verification_support)

    def test_bad_or_missing_file_stops_main_before_schema_or_listener(self):
        for path in (self.root / "missing", self.path):
            if path == self.path:
                path.write_text("invalid public configuration")
            with self.subTest(path=path.name), patch.dict(os.environ, self.values | {KEY:str(path)}, clear=True), \
                    patch.object(server, "read_cpk_control_configuration", return_value=receiving_fixture().config), \
                    patch.object(server, "_install_operations_schema") as schema, \
                    patch.object(server, "create_app") as create, patch.object(server.uvicorn, "run") as listen:
                self.assertEqual(server.main(), 2)
                schema.assert_not_called()
                create.assert_not_called()
                listen.assert_not_called()

    def test_ordinary_main_builds_real_factory_with_single_registered_sender(self):
        factories = []
        constructions = {}
        application = importlib.import_module("control_plane_kit_servers_cpk_server.operations_application")
        def delegate(name):
            constructor = getattr(application, name)
            constructions[name] = []
            def observed(*args, **kwargs):
                value = constructor(*args, **kwargs)
                constructions[name].append((args, kwargs, value))
                return value
            return observed
        actual_factory = server.OperationsApplicationFactory
        def factory(*args, **kwargs):
            value = actual_factory(*args, **kwargs)
            factories.append(value)
            return value
        provider = SimpleNamespace(authorized_resolver=Mock(), metadata_reader=None,
            secret_custodian=None, delegation_key_generator=None)
        permissions = importlib.import_module("control_plane_kit_operations.workspace_permissions")
        with patch.dict(os.environ, self.values, clear=True), \
                patch.object(server, "read_cpk_control_configuration", return_value=receiving_fixture().config), \
                patch.object(server, "_install_operations_schema"), \
                patch.object(permissions.WorkspacePermissionReadService, "installation"), \
                patch.object(server.psycopg, "connect", side_effect=AssertionError("unexpected database I/O")), \
                patch.object(server, "_secret_provider_composition", return_value=provider), \
                patch.object(server, "OperationsApplicationFactory", side_effect=factory), \
                patch.object(application, "ExecutionAdmissionCommandService", side_effect=delegate("ExecutionAdmissionCommandService")), \
                patch.object(application, "ExecutionInvocationService", side_effect=delegate("ExecutionInvocationService")), \
                patch.object(application, "RuntimeInterpreterDispatcher", side_effect=delegate("RuntimeInterpreterDispatcher")), \
                patch.object(server.uvicorn, "run") as listen:
            self.assertEqual(server.main(), 0)
        listen.assert_called_once()
        self.assertIsNotNone(listen.call_args.args[0].state.http_boundary)
        self.assertIsNotNone(listen.call_args.args[0].state.mcp_boundary)
        factory, = factories
        registration = factory.ports.runtime_interpreters[RuntimeKind.DOCKER]
        for name in ("ExecutionAdmissionCommandService", "ExecutionInvocationService"):
            (args, kwargs, value), = constructions[name]
            self.assertIs(kwargs["managed_verification_registration"], registration)
            self.assertIs(kwargs["http_sample_registration"], registration)
            self.assertIs(kwargs["managed_verification_support"], registration.adapter.managed_verification_support)
        (args, kwargs, dispatcher), = constructions["RuntimeInterpreterDispatcher"]
        self.assertIs(args[0][RuntimeKind.DOCKER], registration)
        self.assertIs(dispatcher.interpreters[RuntimeKind.DOCKER], registration)
