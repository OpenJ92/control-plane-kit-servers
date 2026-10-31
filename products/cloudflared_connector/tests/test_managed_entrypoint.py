"""#284 entrypoint laws, using real SDK configuration and a mocked effect owner."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import importlib
import io
import os
from pathlib import Path
import runpy
import tempfile
import threading
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_server_sdk import wrapper
from control_plane_kit_servers_cloudflared_connector import coordinator, entrypoint
from managed_control_fixtures import fixture


MODULE = "control_plane_kit_servers_cloudflared_connector.entrypoint"
CONFIG_ENV = "CPK_WRAPPER_CONFIGURATION_FILE"


class EntrypointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "control.json"
        self.configuration = fixture().config
        self.write_configuration(self.configuration)
        # Deliberately absent: token bytes are native-owned, not loader inputs.
        self.token_path = str(Path(self.directory.name) / "native-token")
        self.environment = {
            CONFIG_ENV: str(self.path), "TUNNEL_TOKEN_FILE": self.token_path,
            "TUNNEL_TOKEN": "PRIVATE_TOKEN_VALUE",
        }

    def write_configuration(self, configuration):
        if self.path.exists():
            self.path.chmod(0o644)
        self.path.write_bytes(core.ReceiverNodeControlConfigurationCodec().encode_bytes(configuration))
        self.path.chmod(0o444)

    def test_real_configuration_loaded_once_and_result_preserved_on_main_thread(self):
        for result in (0, 1, 7, 124, 143):
            with self.subTest(result=result):
                observed = []

                def run(configuration, *, token_path):
                    observed.append((configuration, token_path, threading.current_thread()))
                    return result

                with patch.dict(os.environ, self.environment, clear=True), \
                        patch.object(wrapper, "load_wrapper_configuration",
                                     wraps=wrapper.load_wrapper_configuration) as load, \
                        patch.object(coordinator, "run", side_effect=run) as owner:
                    self.assertEqual(entrypoint.main(), result)
                    load.assert_called_once_with()
                    owner.assert_called_once()
                self.assertEqual(observed, [
                    (self.configuration, self.token_path, threading.main_thread())])
                self.assertFalse(Path(self.token_path).exists())

    def assert_refusal(self, environment):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, environment, clear=True), \
                patch.object(coordinator, "run") as owner, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(entrypoint.main(), 1)
            owner.assert_not_called()
        output = stdout.getvalue() + stderr.getvalue()
        self.assertLessEqual(len(output.encode("utf-8")), 256)
        candidates = tuple(
            value for name in (CONFIG_ENV, "TUNNEL_TOKEN_FILE")
            if isinstance(value := environment.get(name), str) and value
        )
        for private in ("PRIVATE", str(self.path), self.token_path, *candidates):
            self.assertNotIn(private, output)

    def test_missing_configuration_binding_refuses_before_coordinator(self):
        environment = dict(self.environment)
        del environment[CONFIG_ENV]
        self.assert_refusal(environment)

    def test_missing_file_malformed_file_and_wrong_mode_refuse_before_coordinator(self):
        self.path.unlink()
        self.assert_refusal(self.environment)
        self.path.write_text("PRIVATE_INVALID_CONFIGURATION", encoding="utf-8")
        self.path.chmod(0o444)
        self.assert_refusal(self.environment)
        self.write_configuration(self.configuration)
        self.path.chmod(0o600)
        self.assert_refusal(self.environment)

    def test_symlink_configuration_refuses_before_coordinator(self):
        link = self.path.with_name("control-link.json")
        link.symlink_to(self.path)
        self.assert_refusal({**self.environment, CONFIG_ENV: str(link)})

    def test_common_configuration_with_wrong_product_surface_refuses_before_coordinator(self):
        declaration = self.configuration.declaration
        descriptor = replace(
            declaration.surface, health_reads=(core.NodeHealthReadKind.READINESS,))
        self.write_configuration(replace(
            self.configuration, declaration=replace(declaration, surface=descriptor)))
        self.assert_refusal(self.environment)

    def test_missing_empty_and_relative_token_path_refuse_before_coordinator(self):
        for value in (None, "", "PRIVATE_RELATIVE_TOKEN"):
            with self.subTest(value=value):
                environment = dict(self.environment)
                if value is None:
                    del environment["TUNNEL_TOKEN_FILE"]
                else:
                    environment["TUNNEL_TOKEN_FILE"] = value
                self.assert_refusal(environment)

    def test_loader_exception_is_bounded_and_does_not_reach_coordinator(self):
        with patch.object(wrapper, "load_wrapper_configuration",
                          side_effect=OSError("PRIVATE_LOADER_ERROR")):
            self.assert_refusal(self.environment)

    def test_import_does_not_load_configuration_or_launch_effects(self):
        with patch.object(wrapper, "load_wrapper_configuration") as load, \
                patch.object(coordinator, "run") as run, \
                patch("subprocess.Popen") as spawn, \
                patch("socket.socket") as socket:
            importlib.reload(entrypoint)
        load.assert_not_called()
        run.assert_not_called()
        spawn.assert_not_called()
        socket.assert_not_called()

    def test_module_execution_exits_with_coordinator_result(self):
        with patch.dict(os.environ, self.environment, clear=True), \
                patch.object(coordinator, "run", return_value=124) as run:
            with self.assertRaises(SystemExit) as exited:
                runpy.run_module(MODULE, run_name="__main__")
            self.assertEqual(exited.exception.code, 124)
            run.assert_called_once()
