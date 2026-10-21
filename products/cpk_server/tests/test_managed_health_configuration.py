"""Closed startup configuration laws; effects remain with existing owners."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_interpreters.docker import DockerSdkClient, DockerUnixSocketClientConfig
from control_plane_kit_operations.effect_outcome_evidence import NativeConnectionOutcome
from managed_native_material import NativeMaterial
from cpk_http_host_fixtures import fixture
from test_http_mcp_boundaries import DeterministicVerifier
from test_secret_provider_bootstrap import _provider_environment

MODULE = "control_plane_kit_servers_cpk_server.managed_health_configuration"
ERROR = "managed health process configuration is invalid"
MAX_BYTES = 1_048_576


class ManagedHealthConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE),
            "managed health process configuration interface is missing")
        self.api = importlib.import_module(MODULE)
        self.server = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        for name in ("ManagedHealthProcessConfiguration", "decode_managed_health_process_configuration",
                "read_managed_health_process_configuration"):
            self.assertTrue(callable(getattr(self.api, name, None)), "missing configuration API: " + name)
        self.world = NativeMaterial()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "managed.json"
        self.write()

    def document(self, world=None):
        world = world or self.world
        return {"schema": "cpk-server.managed-health.v1",
            "docker": {"socket_path": "/var/run/startup-private.sock", "request_timeout": 5.0},
            "scopes": [{"workspace_id": "workspace-a", "runtime_id": "docker",
                "authority_ref": world.authority.authority_ref.reference_id}],
            "gateway_documents": [world.authored.documents["gateway"].content.decode("utf-8")],
            "native_product_document": world.document.content.decode("utf-8")}

    def encoded(self, document=None):
        return json.dumps(self.document() if document is None else document).encode("utf-8")

    def write(self, world=None):
        self.path.write_bytes(self.encoded(self.document(world)))

    def decode(self, raw=None):
        return self.api.decode_managed_health_process_configuration(self.encoded() if raw is None else raw)

    def environment(self, **changes):
        return {**_provider_environment(Path(self.directory.name) / "unread-provider.token"),
            "CPK_MANAGED_HEALTH": "docker-unix-v1",
            "CPK_MANAGED_HEALTH_CONFIGURATION_FILE": str(self.path), **changes}

    def invalid(self, raw):
        with self.assertRaises(ValueError) as raised:
            self.decode(raw)
        self.assertEqual(str(raised.exception), ERROR)
        self.assertIsNone(raised.exception.__context__)

    def compose(self, config):
        # Capture the real public factory inputs, then run the real factory.
        # Only external schema/credential/database effects are substituted.
        factories = []
        actual = self.server.OperationsApplicationFactory
        provider = SimpleNamespace(authorized_resolver=Mock(), metadata_reader=None, secret_custodian=None)
        def factory(*args, **kwargs):
            value = actual(*args, **kwargs)
            factories.append(value)
            return value
        with patch.object(self.server, "_install_operations_schema") as schema, \
                patch.object(self.server, "_secret_provider_composition", return_value=provider), \
                patch.object(self.server.psycopg, "connect", side_effect=AssertionError("unexpected database I/O")), \
                patch.object(self.server, "OperationsApplicationFactory", side_effect=factory):
            app = self.server.create_app(config, DeterministicVerifier(), control=fixture().config)
        self.assertEqual(len(factories), 1)
        schema.assert_called_once()
        self.assertIsNotNone(app.state.http_boundary)
        return factories[0]

    def test_decode_is_pure_frozen_redacted_and_preserves_one_policy_identity(self):
        with patch("docker.DockerClient") as constructor, patch("docker.from_env") as ambient, \
                patch("builtins.open") as files:
            value = self.decode()
        constructor.assert_not_called()
        ambient.assert_not_called()
        files.assert_not_called()
        self.assertIs(type(value), self.api.ManagedHealthProcessConfiguration)
        binding, = value.provider_clients.bindings
        self.assertIs(binding.local_client_config, value.local_client_config)
        self.assertEqual(value.gateway_documents, (self.world.authored.documents["gateway"],))
        self.assertEqual(value.native_product_document, self.world.document)
        self.assertNotIn("startup-private", repr(value))
        self.assertNotIn("gateway_documents", repr(value))
        with self.assertRaises(AttributeError):
            value.native_product_document = self.world.document

    def test_decoder_rejects_closed_shape_duplicate_keys_and_nonfinite_numbers(self):
        document = self.document()
        raws = [b"[]", b"null", b"{", self.encoded({**document, "unknown": "private-input"}),
            self.encoded({key: value for key, value in document.items() if key != "schema"}),
            self.encoded({**document, "schema": "other"}),
            self.encoded().replace(b'"schema":', b'"schema":"duplicate", "schema":', 1),
            self.encoded().replace(b'"request_timeout": 5.0', b'"request_timeout":5.0,"request_timeout":5.0')]
        for number in (True, None, 0, -1, 61, float("nan"), float("inf")):
            raws.append(self.encoded({**document, "docker": {**document["docker"], "request_timeout": number}}))
        for raw in raws:
            with self.subTest(raw_length=len(raw)):
                self.invalid(raw)

    def test_decoder_enforces_byte_count_scope_and_policy_bounds(self):
        document = self.document()
        for raw in (b"", b" " * (MAX_BYTES + 1), "not bytes"):
            self.invalid(raw)
        for field in ("scopes", "gateway_documents"):
            for value in ([], "wrong"):
                self.invalid(self.encoded({**document, field: value}))
        scope, = document["scopes"]
        scopes = [{**scope, "runtime_id": "runtime-" + str(i)} for i in range(65)]
        gateway = self.world.authored.documents["gateway"].product
        gateways = [ProductDescriptorCodec().encode_document(replace(gateway,
            identity=replace(gateway.identity, contract_revision=i + 1))).content.decode("utf-8")
            for i in range(65)]
        self.invalid(self.encoded({**document, "scopes": scopes}))
        self.invalid(self.encoded({**document, "gateway_documents": gateways}))
        self.assertEqual(len(self.decode(self.encoded({**document, "scopes": scopes[:64]})).provider_clients.bindings), 64)
        self.assertEqual(len(self.decode(self.encoded({**document, "gateway_documents": gateways[:64]})).gateway_documents), 64)
        for scopes in ([scope, scope], [{**scope, "workspace_id": "x" * 129}],
                [{**scope, "runtime_id": "contains space"}], [{**scope, "extra": "private"}]):
            self.invalid(self.encoded({**document, "scopes": scopes}))
        for docker in ({**document["docker"], "socket_path": "relative.sock"},
                {**document["docker"], "unknown": True}):
            self.invalid(self.encoded({**document, "docker": docker}))

    def test_decoder_rejects_noncanonical_duplicate_and_wrong_gateway_documents(self):
        document = self.document()
        for native in (document["native_product_document"] + "\n", {}, "private invalid document"):
            self.invalid(self.encoded({**document, "native_product_document": native}))
        for gateways in ([document["gateway_documents"][0] + "\n"], document["gateway_documents"] * 2,
                [document["native_product_document"]]):
            self.invalid(self.encoded({**document, "gateway_documents": gateways}))

    def test_direct_configuration_rejects_equal_but_independent_policy_and_borrowed_binding(self):
        from control_plane_kit_servers_cpk_server.managed_health_placement import (
            DockerRuntimeClientBinding, DockerRuntimeClientSelector,
        )
        value = self.decode()
        binding, = value.provider_clients.bindings
        other = DockerUnixSocketClientConfig(value.local_client_config.socket_path,
            value.local_client_config.request_timeout)
        self.assertEqual(other, value.local_client_config)
        for provider in (replace(binding, local_client_config=other),
                DockerRuntimeClientBinding(binding.workspace_id, binding.runtime_id, binding.authority_ref,
                    DockerSdkClient(client=SimpleNamespace(api=Mock()), connect_on_init=False))):
            with self.assertRaises(ValueError) as raised:
                replace(value, provider_clients=DockerRuntimeClientSelector((provider,)))
            self.assertEqual(str(raised.exception), ERROR)

    def test_regular_file_is_opened_once_and_descriptor_is_closed(self):
        opened, attempted_flags = [], []
        actual_open = os.open
        def capture(path, flags, *args, **kwargs):
            attempted_flags.append(flags)
            fd = actual_open(path, flags, *args, **kwargs)
            opened.append(fd)
            return fd
        with patch.object(os, "open", side_effect=capture):
            observed = self.api.read_managed_health_process_configuration(str(self.path))
        self.assertEqual(observed.native_product_document, self.world.document)
        self.assertEqual(len(opened), 1)
        required = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        self.assertEqual(attempted_flags[0] & required, required)
        with self.assertRaises(OSError):
            os.fstat(opened[0])

    def test_file_boundary_refuses_symlink_fifo_directory_empty_and_oversize(self):
        link = Path(self.directory.name) / "link.json"
        link.symlink_to(self.path)
        fifo = Path(self.directory.name) / "fifo"
        os.mkfifo(fifo)
        empty = Path(self.directory.name) / "empty"
        empty.write_bytes(b"")
        huge = Path(self.directory.name) / "huge"
        huge.write_bytes(b" " * (MAX_BYTES + 1))
        actual_open = os.open
        required = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        def bounded_open(path, flags, *args, **kwargs):
            attempted_flags.append(flags)
            # A sentinel prevents a broken reader from hanging/following links.
            # The actual flags assertion is outside its redaction boundary.
            if flags & required != required:
                raise OSError("unsafe test open prevented")
            fd = actual_open(path, flags, *args, **kwargs)
            opened.append(fd)
            return fd
        for path in (link, fifo, Path(self.directory.name), empty, huge):
            attempted_flags, opened = [], []
            with self.subTest(kind=path.name), patch.object(os, "open", side_effect=bounded_open):
                with self.assertRaises(ValueError) as raised:
                    self.api.read_managed_health_process_configuration(str(path))
                self.assertEqual(str(raised.exception), ERROR)
                self.assertIsNone(raised.exception.__context__)
                self.assertEqual(len(attempted_flags), 1)
                self.assertEqual(attempted_flags[0] & required, required)
                for fd in opened:
                    with self.assertRaises(OSError):
                        os.fstat(fd)
        for path in ("relative.json", "", "/tmp/private\nname", None, "/" + "x" * 4096):
            with patch.object(os, "open", side_effect=OSError("test open forbidden")) as opened:
                with self.assertRaises(ValueError):
                    self.api.read_managed_health_process_configuration(path)
            opened.assert_not_called()

    def test_growth_and_read_failure_close_the_same_opened_descriptor(self):
        for fault in ("growth", "read"):
            with self.subTest(fault=fault):
                self.write()
                opened = []
                actual_open, actual_stat = os.open, os.fstat
                def capture(path, flags, *args, **kwargs):
                    fd = actual_open(path, os.O_WRONLY if fault == "read" else flags, *args, **kwargs)
                    opened.append(fd)
                    return fd
                def stat(fd):
                    value = actual_stat(fd)
                    if fault == "growth":
                        with self.path.open("ab") as stream:
                            stream.write(b" " * (MAX_BYTES + 1))
                    return value
                with patch.object(os, "open", side_effect=capture), patch.object(os, "fstat", side_effect=stat):
                    with self.assertRaises(ValueError) as raised:
                        self.api.read_managed_health_process_configuration(str(self.path))
                self.assertEqual(str(raised.exception), ERROR)
                self.assertEqual(len(opened), 1)
                with self.assertRaises(OSError):
                    actual_stat(opened[0])

    def test_disabled_environment_keeps_legacy_composition_without_file_access(self):
        environment = self.environment()
        environment.pop("CPK_MANAGED_HEALTH_CONFIGURATION_FILE")
        for enabled in (None, "disabled"):
            values = dict(environment)
            if enabled is None:
                values.pop("CPK_MANAGED_HEALTH")
            else:
                values["CPK_MANAGED_HEALTH"] = enabled
            with patch.object(os, "open") as opened:
                config = self.server.CpkServerBootstrapConfiguration.from_environment(values)
            opened.assert_not_called()
            self.assertIsNone(config.managed_health_process)
            self.assertIsNone(config.managed_health)
            factory = self.compose(config)
            self.assertIsNone(factory.ports.managed_health)
            self.assertIsNone(factory.ports.runtime_interpreters[RuntimeKind.DOCKER].local_client_config)

    def test_environment_mode_and_file_presence_fail_closed(self):
        base = self.environment()
        cases = [{**base, "CPK_MANAGED_HEALTH": mode} for mode in ("disabled", "", "other")]
        cases += [{key: value for key, value in base.items() if key != "CPK_MANAGED_HEALTH_CONFIGURATION_FILE"},
            {**base, "CPK_MANAGED_HEALTH_CONFIGURATION_FILE": ""}]
        for values in cases:
            with self.assertRaises(self.server.BootstrapConfigurationError) as raised:
                self.server.CpkServerBootstrapConfiguration.from_environment(values)
            self.assertEqual(str(raised.exception), ERROR)

    def test_invalid_enabled_prerequisites_stop_before_schema_or_provider_in_both_paths(self):
        valid = self.server.CpkServerBootstrapConfiguration.from_environment(self.environment())
        variants = [dict(runtime_dispatcher=self.server.RuntimeDispatcherBootstrapConfiguration.from_process_value("none")),
            dict(product_material_resolver="none"), dict(product_material_resolver="local-development"),
            dict(managed_health=object())]
        for changes in variants:
            config = replace(valid, **changes)
            with self.subTest(fields=tuple(changes)), patch.object(self.server, "_install_operations_schema") as schema, \
                    patch.object(self.server, "_secret_provider_composition") as provider, \
                    patch("docker.DockerClient") as docker:
                with self.assertRaises(self.server.BootstrapConfigurationError) as raised:
                    self.server.create_app(config, DeterministicVerifier(), control=fixture().config)
                self.assertEqual(str(raised.exception), ERROR)
                schema.assert_not_called()
                provider.assert_not_called()
                docker.assert_not_called()
        for values in (self.environment(CPK_RUNTIME_INTERPRETERS="none"),
                {key: value for key, value in self.environment(CPK_PRODUCT_MATERIAL_RESOLVER="none").items()
                    if not key.startswith("CPK_MATERIAL_PROVIDER_")}):
            with self.assertRaises(self.server.BootstrapConfigurationError) as raised:
                self.server.CpkServerBootstrapConfiguration.from_environment(values)
            self.assertEqual(str(raised.exception), ERROR)

    def test_pure_registry_rules_reject_bad_references_urls_and_paths_before_effects(self):
        valid = self.server.CpkServerBootstrapConfiguration.from_environment(self.environment())
        fields = [("CPK_MATERIAL_PROVIDER_ROUTES_JSON", "material_provider_routes_json", {"bad reference": "https://valid.invalid"}),
            ("CPK_MATERIAL_PROVIDER_ROUTES_JSON", "material_provider_routes_json", {"provider-main": "ftp://private.invalid"}),
            ("CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON", "material_provider_bootstrap_files_json", {"bad reference": "/tmp/token"}),
            ("CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON", "material_provider_bootstrap_files_json", {"secret://bootstrap/provider-token": "relative.token"})]
        for environment_field, config_field, value in fields:
            raw = json.dumps(value)
            with self.subTest(field=config_field), patch.object(self.server, "_install_operations_schema") as schema, \
                    patch.object(self.server, "_secret_provider_composition") as provider:
                with self.assertRaises(self.server.BootstrapConfigurationError) as raised:
                    self.server.CpkServerBootstrapConfiguration.from_environment(self.environment(**{environment_field: raw}))
                self.assertEqual(str(raised.exception), ERROR)
                with self.assertRaises(self.server.BootstrapConfigurationError) as raised:
                    self.server.create_app(replace(valid, **{config_field: raw}), DeterministicVerifier(), control=fixture().config)
                self.assertEqual(str(raised.exception), ERROR)
                schema.assert_not_called()
                provider.assert_not_called()

    def test_normal_app_factory_shares_policy_across_all_consumers_without_contact(self):
        with patch("docker.DockerClient") as constructor, patch("docker.from_env") as ambient:
            config = self.server.CpkServerBootstrapConfiguration.from_environment(self.environment())
            factory = self.compose(config)
        policy = config.managed_health_process.local_client_config
        ports = factory.ports
        self.assertIs(ports.runtime_interpreters[RuntimeKind.DOCKER].local_client_config, policy)
        self.assertIs(ports.runtime_observer.local_client_config, policy)
        self.assertIs(ports.managed_health.provider_clients, config.managed_health_process.provider_clients)
        self.assertIs(ports.managed_health.native.provider_clients, ports.managed_health.provider_clients)
        self.assertIsNone(ports.managed_health.endpoints)
        self.assertIsInstance(factory.clock(), str)
        now = ports.managed_health.native.clock()
        self.assertIsInstance(now, datetime)
        self.assertIsNotNone(now.utcoffset())
        constructor.assert_not_called()
        ambient.assert_not_called()

    def test_process_composition_keeps_public_whole_plans_and_refuses_local_requirement(self):
        from control_plane_kit_core.planning import ObserveManagementBootstrap, ManagementBootstrapStage
        for options in ({}, {"retained_image": True}, {"retained": True}):
            world = NativeMaterial(**options)
            self.write(world)
            config = self.server.CpkServerBootstrapConfiguration.from_environment(self.environment())
            with patch("docker.DockerClient") as docker:
                bridge = self.compose(config).ports.managed_health
                selected = bridge.select(**world.selection())
            needs_local = any(type(a.operation) is ObserveManagementBootstrap
                and a.operation.stage is ManagementBootstrapStage.GATEWAY_LOCAL_READY for a in world.plan.activities)
            if needs_local:
                self.assertIsNone(selected)
            else:
                self.assertIsNotNone(selected)
                self.assertIn(world.request.activity_id, selected)
            docker.assert_not_called()

    def test_normal_native_composition_reaches_real_freshness_and_connected_result(self):
        # Runtime-owned pure naming functions construct transport facts; no
        # copied naming algorithm, admitted history or private-helper assertion.
        from control_plane_kit_interpreters.docker.runtime import (
            _container_name, _network_name, _node_labels, _secret_volume_name,
        )
        from control_plane_kit_interpreters.docker.sdk import (
            DockerSdkConnectorInspection, DockerSdkConnectorSample, DockerSdkConnectorImage,
            DockerSdkSecretMount, DockerSdkConnectorConfigurationMount,
            DockerSdkConfigurationMountInspection, DockerSdkConfigurationFileInspection,
        )
        config = self.server.CpkServerBootstrapConfiguration.from_environment(self.environment())
        factory = self.compose(config)
        native = factory.ports.managed_health.native
        world = self.world
        request, artifact = world.request, world.artifact
        material, = request.products
        delivery, = material.product.runtime_contract.secret_deliveries
        now = datetime.now(timezone.utc)
        sample_time = (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        sample = DockerSdkConnectorSample(sample_time, sample_time, 0, json.dumps({
            "schema": "cpk.cloudflared.connection/v1", "outcome": "connected", "readyConnections": 1,
            "connectorId": "ae232234-79c8-48fe-9b67-123456789abc"}))
        facts = DockerSdkConnectorInspection("c" * 64, "/" + _container_name(request, "connector"),
            "sha256:" + "a" * 64, tuple(_node_labels(request, material).items()), "b" * 64,
            _network_name(request, "docker"), DockerSdkSecretMount(delivery.target_path,
                _secret_volume_name(request, "connector", delivery, owner_uid=10002)),
            (now - timedelta(seconds=60)).isoformat().replace("+00:00", "Z"), sample,
            DockerSdkConnectorConfigurationMount(artifact.target_path, "startup-observed-volume"))
        image = DockerSdkConnectorImage(facts.image_id, facts.launch_digest, 10002)
        content = DockerSdkConfigurationMountInspection(facts.container_id, "startup-observed-volume",
            artifact.target_path, "content", True,
            DockerSdkConfigurationFileInspection(artifact.content_digest, int(artifact.file_mode.value, 8), True))
        with patch.object(DockerSdkClient, "inspect_connector_container", return_value=facts) as containers, \
                patch.object(DockerSdkClient, "inspect_connector_image", return_value=image), \
                patch.object(DockerSdkClient, "inspect_configuration_mount", return_value=content), \
                patch("docker.DockerClient") as constructor:
            result = asyncio.run(native.observe_connection(world.realization, request, world.authority))
        self.assertEqual(result.outcome, NativeConnectionOutcome.CONNECTED)
        self.assertEqual(result.effect_id, request.effect_id)
        self.assertEqual((result.sample_start, result.sample_end), (sample_time, sample_time))
        self.assertEqual(containers.call_count, 2)
        constructor.assert_not_called()
        self.assertIsInstance(factory.clock(), str)

    def test_main_uses_enabled_configuration_and_invalid_input_never_starts_listener(self):
        values = self.environment(CPK_CONTROL_AUTH_VERIFIER="static-development",
            CPK_CONTROL_AUTH_STATIC_CREDENTIAL="fixture-credential",
            CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON=json.dumps({"workspace-a": [PolicyScope.INSTANCE_WORKSPACE_EDIT.value]}))
        real_create = self.server.create_app
        captured = []
        def create(config, verifier, **kwargs):
            captured.append(config)
            return real_create(config, verifier, **kwargs)
        provider = SimpleNamespace(authorized_resolver=Mock(), metadata_reader=None, secret_custodian=None)
        with patch.dict(os.environ, values, clear=True), \
                patch.object(self.server, "read_cpk_control_configuration", return_value=fixture().config), \
                patch.object(self.server, "_install_operations_schema"), \
                patch.object(self.server, "_secret_provider_composition", return_value=provider), \
                patch.object(self.server.psycopg, "connect", side_effect=AssertionError("database I/O")), \
                patch.object(self.server, "create_app", side_effect=create), \
                patch.object(self.server.uvicorn, "run") as run:
            self.assertEqual(self.server.main(), 0)
        self.assertIsNotNone(captured[0].managed_health_process)
        run.assert_called_once()
        self.path.write_bytes(b"private malformed configuration")
        with patch.dict(os.environ, values, clear=True), \
                patch.object(self.server, "_install_operations_schema") as schema, \
                patch.object(self.server, "_secret_provider_composition") as provider, \
                patch.object(self.server.uvicorn, "run") as run, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(self.server.main(), 2)
        self.assertIn(ERROR, output.getvalue())
        self.assertNotIn("private malformed", output.getvalue())
        self.assertNotIn(str(self.path), output.getvalue())
        schema.assert_not_called()
        provider.assert_not_called()
        run.assert_not_called()
