"""Managed PostgreSQL composition/startup laws; synthetic images are not releases."""
import copy
from dataclasses import replace
import importlib
import json
from pathlib import Path
import signal
import socket
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import control_plane_kit_core as core
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.products import OciImageReference, ProductDescriptorCodec
from control_plane_kit_core.topology import GraphDescriptorCodec
from control_plane_kit_servers_postgres_server.configuration import (
    postgres_control_configuration_artifact, postgres_control_declaration,
    postgres_source_runtime_contract,
)
from root_complete_fixtures import complete_input, contract, replace_artifact_content
from test_root_bootstrap import DRIVER, installation_input


def managed_input():
    document = complete_input()
    cpk = core.ReceiverNodeControlConfigurationCodec().decode_bytes(
        contract(document, "cpk")["configuration_artifacts"][0]["content"].encode())
    roles = core.NodeControlGraphReferenceRole
    configuration = replace(cpk, target=replace(cpk.target,
        node_id=core.NodeControlGraphReference(roles.NODE, "root-a-postgres"),
        provider_socket_name=core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "management"),
        receiver_id="f" * 32), declaration=postgres_control_declaration())
    artifact = postgres_control_configuration_artifact(configuration)
    codec = ProductDescriptorCodec()
    original = codec.decode_document(document["installation"]["products"]["postgres"])
    product = replace(original.product,
        image=OciImageReference("example.invalid", "fixture/managed-postgres", "sha256:" + "e" * 64),
        runtime_contract=postgres_source_runtime_contract(artifact))
    document["installation"]["products"]["postgres"] = json.loads(codec.encode_document(product).content)
    return document


class ManagedPostgresInstallationTests(unittest.TestCase):
    def setUp(self):
        self.bootstrap = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")
        self.document = managed_input()

    def plan(self, document=None):
        return self.bootstrap.plan_root_bootstrap(self.document if document is None else document,
                                                 driver_image_id=DRIVER)

    def refused(self, document):
        with self.assertRaises(self.bootstrap.RootBootstrapError):
            self.plan(document)

    def test_managed_graph_preserves_file_control_data_and_adds_authenticated_sql(self):
        with patch("socket.socket", side_effect=AssertionError("unexpected network IO")):
            plan = self.plan()
            self.assertEqual(plan, self.plan())
        codec = GraphDescriptorCodec()
        graph = codec.decode(plan["graph"])
        self.assertEqual(codec.encode(graph), plan["graph"])
        postgres = graph.node("root-a-postgres")
        delivery, = postgres.secret_deliveries
        self.assertEqual(delivery.target_path, "/run/secrets/postgres/password")
        self.assertEqual(delivery.file_mode.value, "0400")
        self.assertEqual(delivery.path_binding.environment_name, "POSTGRES_PASSWORD_FILE")
        self.assertEqual(delivery.reference.reference_id,
            self.document["installation"]["references"]["postgres_password"])
        check, = postgres.block_spec.verification.checks
        self.assertEqual(check.provider_socket, "postgres")
        self.assertEqual(check.authentication.password_reference, delivery.reference)
        self.assertEqual((check.authentication.database, check.authentication.username), ("cpk", "cpk"))
        resource = next(node for node in plan["resources"]["nodes"] if node["node_id"] == "root-a-postgres")
        self.assertEqual(resource["configuration_files"][0]["artifact"],
                         contract(self.document, "postgres")["configuration_artifacts"][0])
        self.assertEqual(resource["data_volumes"][0]["target"], "/var/lib/postgresql/data")
        self.assertEqual(len(resource["secret_files"]), 1)
        self.assertNotIn("POSTGRES_PASSWORD", resource["environment"])
        self.assertFalse(any(binding["node_id"] == "root-a-postgres" for binding in plan["host_bindings"]))
        self.assertEqual(graph.public_ingresses, ())
        for role in ("cpk", "secrets"):
            self.assertEqual(plan["input"]["installation"]["products"][role],
                             self.document["installation"]["products"][role])

    def test_target_is_validated_with_or_without_optional_website(self):
        for website in (True, False):
            baseline = copy.deepcopy(self.document)
            if not website:
                del baseline["installation"]["website"]
            self.plan(baseline)
            for field, value in (("workspace_id", "foreign-workspace"), ("runtime_id", "foreign-runtime"),
                    ("node_id", "foreign-node"), ("provider_socket_name", "foreign-socket"),
                    ("receiver_id", "invalid")):
                changed = copy.deepcopy(baseline)
                replace_artifact_content(changed, "postgres", lambda content: content["target"].update({field: value}))
                with self.subTest(website=website, field=field):
                    self.refused(changed)

    def test_receiver_alias_and_missing_verifier_families_are_rejected(self):
        changed = copy.deepcopy(self.document)
        receiver = json.loads(contract(changed, "cpk")["configuration_artifacts"][0]["content"])["target"]["receiver_id"]
        replace_artifact_content(changed, "postgres", lambda content: content["target"].update(receiver_id=receiver))
        self.refused(changed)
        for families in ([], ["workload-node-control-surface-read"], ["workload-node-health-read"]):
            changed = copy.deepcopy(self.document)
            replace_artifact_content(changed, "postgres", lambda content: content.update(verifiers=[
                value for value in content["verifiers"] if value["purpose"] in families]))
            self.refused(changed)

    def test_managed_socket_alone_does_not_admit_wrong_file_identity_or_contract(self):
        codec = ProductDescriptorCodec()
        original = codec.decode_document(self.document["installation"]["products"]["postgres"])
        selected = original.product.runtime_contract
        delivery, = selected.secret_deliveries
        from control_plane_kit_core.secrets import SecretEnvironmentDelivery, SecretFilePathBinding
        changes = [
            {"secret_deliveries": (replace(delivery, target_path="/run/secrets/wrong"),)},
            {"secret_deliveries": (replace(delivery, path_binding=SecretFilePathBinding("WRONG_FILE")),)},
            {"secret_deliveries": (SecretEnvironmentDelivery("POSTGRES_PASSWORD", delivery.reference, delivery.intent),)},
            {"public_environment": tuple(replace(item, value="other") if item.name == "POSTGRES_DB" else item
                                         for item in selected.public_environment)},
            {"configuration_artifacts": ()},
            {"control_surfaces": (), "capabilities": tuple(capability for capability in selected.capabilities
                if capability is not CapabilityName.NODE_CONTROLLABLE)},
        ]
        for change in changes:
            changed = copy.deepcopy(self.document)
            changed["installation"]["products"]["postgres"] = json.loads(codec.encode_document(
                replace(original.product, runtime_contract=replace(selected, **change))).content)
            with self.subTest(field=tuple(change)):
                self.refused(changed)

    def test_native_input_keeps_environment_delivery_and_historical_plan(self):
        plan = self.plan(installation_input())
        graph = GraphDescriptorCodec().decode(plan["graph"])
        delivery, = graph.node("root-a-postgres").secret_deliveries
        self.assertEqual(delivery.environment_name, "POSTGRES_PASSWORD")
        self.assertEqual(plan, self.plan(installation_input()))

    def material_index(self, plan, password):
        root = Path(self.enterContext(TemporaryDirectory(dir=Path.cwd())))
        reference = plan["input"]["installation"]["references"]["postgres_password"]
        files = {}
        for number, selected in enumerate(plan["required_material"]):
            name = "material-" + str(number)
            path = root / name
            path.write_bytes(password if selected == reference else b"fixture-private-material")
            path.chmod(0o400)
            files[selected] = name
        index = root / "index.json"
        index.write_text(json.dumps({"schema": "cpk.root-bootstrap.material.v1", "files": files}))
        index.chmod(0o400)
        return index

    def test_ambiguous_managed_shared_password_is_refused_before_acquisition(self):
        runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        plan = self.plan()
        for password in (b"private-canary\n", b"private-canary\n\n", b"", b"private\x00canary", b"\xff"):
            index = self.material_index(plan, password)
            state = index.parent / "state"
            with patch.object(runtime, "_acquire") as acquire:
                with self.assertRaises(self.bootstrap.RootBootstrapError) as raised:
                    self.bootstrap.apply_root_bootstrap(plan, expected_digest=plan["digest"],
                        driver_image_id=DRIVER, index_path=index, state_directory=state)
                acquire.assert_not_called()
            self.assertNotIn("canary", str(raised.exception))
            self.assertFalse((state / "receipt.json").exists())

    def test_shared_credential_resolution_preserves_identical_recipient_and_probe_bytes(self):
        from control_plane_kit_core.secrets import (
            LocalDevelopmentSecretResolver, SecretEnvironmentDelivery,
            SecretProviderAuthority,
        )
        from control_plane_kit_interpreters.secrets import resolve_secret_deliveries
        from control_plane_kit_servers_postgres_server.readiness import psql_invocation
        runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        for managed, password in ((True, b"private-password-canary"), (False, b"native-password\n")):
            plan = self.plan() if managed else self.plan(installation_input())
            material = runtime._material(plan, self.material_index(plan, password))
            graph = GraphDescriptorCodec().decode(plan["graph"])
            pg_delivery, = graph.node("root-a-postgres").secret_deliveries
            reference = pg_delivery.reference
            resolver = LocalDevelopmentSecretResolver(SecretProviderAuthority(reference.provider_id, (reference.path,)),
                {reference.reference_id: material[reference.reference_id]})
            cpk_delivery, = tuple(delivery for delivery in graph.node("root-a-cpk").secret_deliveries
                if isinstance(delivery, SecretEnvironmentDelivery) and delivery.environment_name == "PGPASSWORD")
            cpk = resolve_secret_deliveries((cpk_delivery,), resolver=resolver).environment["PGPASSWORD"]
            pg = resolve_secret_deliveries((pg_delivery,), resolver=resolver)
            pg_value = pg.files[0].value.reveal() if managed else pg.environment["POSTGRES_PASSWORD"]
            self.assertEqual(cpk.encode(), password)
            self.assertEqual(pg_value, cpk)
            if managed:
                self.assertEqual(psql_invocation(material[reference.reference_id].encode()).environ["PGPASSWORD"], cpk)


class ManagedPostgresStartupTests(unittest.TestCase):
    def setUp(self):
        self.runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
        self.container = Mock()

    def test_listener_or_failed_query_is_not_startup_success(self):
        for result in (SimpleNamespace(exit_code=0, output=b""),
                       SimpleNamespace(exit_code=1, output=b"private-error-canary"),
                       SimpleNamespace(exit_code=0, output=b"2\n")):
            self.container.exec_run.return_value = result
            with patch.object(self.runtime.time, "sleep"), patch.object(self.runtime.time, "monotonic", side_effect=[0, 0, 61]):
                with self.assertRaises(self.runtime.RootBootstrapHold) as raised:
                    self.runtime._postgres_ready(self.container, password=b"private-password-canary")
            self.assertNotIn("canary", str(raised.exception))
            args, kwargs = self.container.exec_run.call_args
            self.assertNotIn("private-password-canary", repr(args))
            self.assertEqual(kwargs["environment"]["PGPASSWORD"], "private-password-canary")
            self.assertFalse(kwargs["stderr"])

    def test_only_exact_authenticated_select_one_succeeds(self):
        previous = signal.getsignal(signal.SIGALRM)
        self.container.exec_run.side_effect = [SimpleNamespace(exit_code=1, output=b""),
                                              SimpleNamespace(exit_code=0, output=b"1\n")]
        with patch.object(self.runtime.time, "sleep"):
            self.runtime._postgres_ready(self.container, password=b"private-password-canary")
        self.assertEqual(self.container.exec_run.call_count, 2)
        args, kwargs = self.container.exec_run.call_args
        self.assertIn("SET statement_timeout = '2s'; SELECT 1;", args[0])
        self.assertEqual(kwargs["environment"]["PGCONNECT_TIMEOUT"], "2")
        self.assertIs(signal.getsignal(signal.SIGALRM), previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_native_readiness_remains_the_existing_command(self):
        self.container.exec_run.return_value = SimpleNamespace(exit_code=0)
        self.runtime._postgres_ready(self.container)
        self.container.exec_run.assert_called_once_with(["pg_isready", "-h", "127.0.0.1"])

    def test_uncertain_daemon_call_is_redacted_and_not_retried(self):
        previous = signal.getsignal(signal.SIGALRM)
        self.container.exec_run.side_effect = TimeoutError("private-error-canary")
        with self.assertRaises(self.runtime.RootBootstrapHold) as raised:
            self.runtime._postgres_ready(self.container, password=b"private-password-canary")
        self.assertNotIn("canary", str(raised.exception))
        self.container.exec_run.assert_called_once()
        self.assertIs(signal.getsignal(signal.SIGALRM), previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_stalled_sdk_frame_read_is_interrupted_closed_and_never_replayed(self):
        from docker.api.client import APIClient
        reader, writer = socket.socketpair()
        response = SimpleNamespace(close=Mock(side_effect=reader.close))
        client = SimpleNamespace(_get_raw_response_socket=lambda _response: reader)
        # Exercise the actual SDK's unbounded poll/select reader. The peer sends
        # no frames. A watchdog only prevents a broken test from hanging CI.
        def blocked(*_args, **_kwargs):
            output = APIClient._read_from_socket(client, response, stream=False, tty=False)
            return SimpleNamespace(exit_code=0, output=output)
        self.container.exec_run.side_effect = blocked
        watchdog = threading.Timer(2, writer.close)
        watchdog.start()
        previous = signal.getsignal(signal.SIGALRM)
        started = time.monotonic()
        try:
            with patch.object(self.runtime, "_POSTGRES_OBSERVATION_SECONDS", 0.05):
                with self.assertRaises(self.runtime.RootBootstrapHold) as raised:
                    self.runtime._postgres_ready(self.container, password=b"private-password-canary")
            self.assertLess(time.monotonic() - started, 1)
            self.assertNotIn("canary", str(raised.exception))
            self.container.exec_run.assert_called_once()
            response.close.assert_called_once()
            self.assertEqual(reader.fileno(), -1)
            self.assertIs(signal.getsignal(signal.SIGALRM), previous)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        finally:
            watchdog.cancel()
            watchdog.join(timeout=1)
            writer.close()
            reader.close()
        self.assertFalse(watchdog.is_alive())

    def test_existing_timer_is_preserved_and_refuses_before_exec(self):
        try:
            signal.setitimer(signal.ITIMER_REAL, 30)
            with self.assertRaises(self.runtime.RootBootstrapHold):
                self.runtime._postgres_ready(self.container, password=b"private-password-canary")
            self.container.exec_run.assert_not_called()
            self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0], 0)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    def test_timer_setup_failure_restores_handler_and_refuses_before_exec(self):
        previous = signal.getsignal(signal.SIGALRM)
        with patch.object(self.runtime.signal, "setitimer", side_effect=[ValueError("private-canary"), None]):
            with self.assertRaises(self.runtime.RootBootstrapHold) as raised:
                self.runtime._postgres_ready(self.container, password=b"private-password-canary")
        self.assertNotIn("canary", str(raised.exception))
        self.container.exec_run.assert_not_called()
        self.assertIs(signal.getsignal(signal.SIGALRM), previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_non_main_thread_refuses_before_exec(self):
        failures = []
        def observe():
            try:
                self.runtime._postgres_ready(self.container, password=b"private-password-canary")
            except self.runtime.RootBootstrapHold:
                failures.append("held")
        thread = threading.Thread(target=observe)
        thread.start()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, ["held"])
        self.container.exec_run.assert_not_called()
