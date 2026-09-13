from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationArtifact
from control_plane_kit_core.products import ProductRuntimeContractCodec, ProductDescriptorCodec
from control_plane_kit_servers_http_active_router import configuration as config
from control_plane_kit_servers_http_active_router import server as router
from router_control_fixtures import fixture, running, request, token


class RouterControlTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture()
        self.config = self.fixture.config
        self.artifact = config.router_control_configuration_artifact(self.config)

    def rejected(self, action):
        with self.assertRaises(config.RouterConfigurationError) as caught:
            action()
        self.assertEqual(str(caught.exception), "Router control configuration is invalid")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(vars(caught.exception), {})

    def test_configuration_artifact_and_source_contract_are_real_values(self):
        self.assertEqual(config.decode_router_control_configuration(self.artifact.content.encode()), self.config)
        self.assertEqual(ConfigurationArtifact.from_descriptor(self.artifact.descriptor()), self.artifact)
        self.assertEqual(self.artifact.target_path, "/etc/cpk/router/control.json")
        self.assertEqual(self.artifact.file_mode.value, "0444")
        contract = config.router_source_runtime_contract(self.artifact)
        self.assertEqual(ProductRuntimeContractCodec().decode(contract.descriptor()), contract)
        self.assertEqual(contract.control_surfaces, (self.config.declaration.surface,))
        self.assertEqual(contract.provider_ports[0].container_port, 8000)
        self.assertEqual(contract.configuration_artifacts, (self.artifact,))
        self.assertIn("node-controllable", [c.value for c in contract.capabilities])
        descriptor = Path(__file__).resolve().parents[1] / "product.cpk.json"
        old = ProductDescriptorCodec().decode_document(descriptor.read_bytes()).product
        self.assertEqual(old.identity.contract_revision, 1)
        self.assertEqual(old.runtime_contract.control_surfaces, ())
        self.assertEqual(old.runtime_contract.configuration_artifacts, ())
        self.assertEqual(contract.verification, old.runtime_contract.verification)
        self.assertNotIn("public_key", repr(self.config))
        result = subprocess.run([sys.executable, "-I", "-B", "-c",
            "import sys; import control_plane_kit_servers_http_active_router.configuration; "
            "assert 'control_plane_kit_servers_http_active_router.server' not in sys.modules"],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_closed_configuration_rejects_invalid_keys_identity_and_oversize(self):
        original = json.loads(self.artifact.content)
        raw_cases = [b"", b"\xff", b"{" + b" " * 65536,
                     b'{"profile":"router-control-unconfigured.v1"}',
                     self.artifact.content.replace('"profile":', '"profile":"duplicate", "profile":', 1).encode()]
        for field, value in (("runtime_id", ""), ("extra", True), ("profile", "unknown"),
                             ("target", {**original["target"], "provider_socket_name":"elsewhere"}),
                             ("declaration", {**original["declaration"], "profile":"workload-node-control-surface-declaration.v1"}),
                             ("surface_read", {"issuer":"x", "public_keys":[]}),
                             ("health_read", {**original["health_read"], "public_keys":[
                                 {**original["health_read"]["public_keys"][0], "public_key_pem":"private malformed key"}]}),
                             ("health_read", {**original["health_read"], "purpose":"workload-node-control"}),
                             ("health_read", {"issuer":"secret\nissuer", "public_keys":original["health_read"]["public_keys"]}),
                             ("health_read", {**original["health_read"], "public_keys":original["health_read"]["public_keys"] * 17})):
            raw_cases.append(json.dumps({**original, field:value}).encode())
        for raw in raw_cases:
            with self.subTest(size=len(raw)):
                self.rejected(lambda: config.decode_router_control_configuration(raw))
        self.rejected(lambda: config.router_control_configuration_artifact(None))
        self.rejected(lambda: config.router_source_runtime_contract(None))
        interrupted = KeyboardInterrupt()
        with patch.object(config.json, "loads", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt) as caught:
                config.decode_router_control_configuration(self.artifact.content.encode())
            self.assertIs(caught.exception, interrupted)
        with patch.object(router, "ThreadingHTTPServer") as listener:
            self.rejected(lambda: router.create_router_server(None, config.RouterSettings("http://upstream.invalid")))
            listener.assert_not_called()

    def test_fixed_file_checks_opened_regularity_symlinks_and_exact_byte_boundary(self):
        raw = self.artifact.content.encode()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "control.json"
            with patch.object(config, "CONTROL_PATH", str(path)):
                self.rejected(config.read_router_control_configuration)
                path.write_bytes(raw + b" " * (65536 - len(raw)))
                self.assertEqual(config.read_router_control_configuration(), self.config)
                with path.open("ab") as stream:
                    stream.write(b" ")
                self.rejected(config.read_router_control_configuration)
                path.unlink()
                target = Path(directory) / "target"
                target.write_bytes(raw)
                path.symlink_to(target)
                self.rejected(config.read_router_control_configuration)
                path.unlink()
                path.mkdir()
                self.rejected(config.read_router_control_configuration)
                path.rmdir()
                os.mkfifo(path)
                self.rejected(config.read_router_control_configuration)
                path.unlink()
                path.write_bytes(raw)
                replacement = Path(directory) / "replacement"
                replacement.write_bytes(b"unconfigured")
                real_open = os.open
                def swap_after_open(name, flags):
                    descriptor = real_open(name, flags)
                    replacement.replace(path)
                    return descriptor
                with patch.object(config.os, "open", side_effect=swap_after_open):
                    self.assertEqual(config.read_router_control_configuration(), self.config)
                self.rejected(config.read_router_control_configuration)

    def test_passive_installation_bind_failure_and_production_port_policy(self):
        captured = []
        real = router.ThreadingHTTPServer
        def create(*args, **kwargs):
            host = real(*args, **kwargs)
            captured.append(host)
            self.assertEqual(host.socket.getsockname()[1], 0)
            return host
        for failure in ("install_router_control", "server_bind", "server_activate"):
            with self.subTest(stage=failure), patch.object(router, "ThreadingHTTPServer", side_effect=create):
                owner = router if failure == "install_router_control" else real
                with patch.object(owner, failure, side_effect=RuntimeError("test startup failure")):
                    with self.assertRaises(RuntimeError):
                        router.create_router_server(self.config, config.RouterSettings("http://upstream.invalid"), address=("127.0.0.1", 0))
                self.assertEqual(captured[-1].socket.fileno(), -1)
        for port in ("8001", "0", "invalid"):
            with patch.dict(os.environ, {"PORT":port, "ACTIVE_TARGET_URL":"http://upstream.invalid"}), patch.object(router, "ThreadingHTTPServer") as listener:
                self.assertEqual(router.main(), 2)
                listener.assert_not_called()
        with patch.dict(os.environ, {"PORT":"8000", "ACTIVE_TARGET_URL":"http://upstream.invalid"}), \
                patch.object(router, "read_router_control_configuration", return_value=self.config), \
                patch.object(router, "create_router_server") as create_host:
            create_host.return_value.serve_forever.side_effect = KeyboardInterrupt
            self.assertEqual(router.main(), 0)
            self.assertEqual(create_host.call_args.kwargs["address"], ("0.0.0.0", 8000))
            create_host.return_value.server_close.assert_called_once()

    def test_reserved_reads_and_denials_never_forward(self):
        live = "/__control/health/liveness"
        with patch.object(router, "forward", return_value=(200, b"application", "text/plain")) as forward, \
                running(self, self.fixture) as host:
            static = request(host, "/__control/capabilities", token(self.fixture, static=True))
            self.assertEqual(static[0], 200)
            self.assertEqual(json.loads(static[1])["declaration"], self.config.declaration.descriptor())
            status, body, headers = request(host, live, token(self.fixture))
            self.assertEqual(status, 200)
            result = core.NodeHealthReadResultCodec().decode(json.loads(body))
            self.assertIs(result.outcome, core.NodeHealthReadOutcome.HEALTHY)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(self.config.declaration.surface.health_reads, (core.NodeHealthReadKind.LIVENESS,))
            # An authentic, correctly signed READINESS grant tests the undeclared kind,
            # independently of missing-token and unknown reserved-path rejection.
            readiness = token(self.fixture, kind=core.NodeHealthReadKind.READINESS)
            self.assertNotEqual(request(host, "/__control/health/readiness", readiness)[0], 200)
            for changes in (
                {"target":replace(self.config.target, node_id=core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.NODE,"other"))},
                {"runtime_id":core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.RUNTIME,"other")},
                {"declaration_identity":core.WorkloadNodeControlSurfaceDeclarationIdentity("0" * 64)},
            ):
                self.assertNotEqual(request(host, live, token(self.fixture, request_changes=changes))[0], 200)
            for credential in (None, "invalid", token(self.fixture, static=True)):
                self.assertNotEqual(request(host, live, credential)[0], 200)
            for path, method in (("/__control/health/ready", "GET"),
                                 ("/__control/variables/x", "POST"),
                                 ("/__control/health/liveness", "PUT"),
                                 ("/%5f_control/health/liveness", "GET"),
                                 ("/__control/health/liveness?unexpected=1", "GET")):
                self.assertNotEqual(request(host, path, token(self.fixture), method)[0], 200)
            forward.assert_not_called()
            self.assertEqual(request(host, "/health/live")[:2], (200, b"live\n"))
            forward.assert_not_called()
            self.assertEqual(request(host, "/health/ready", "application-token")[:2], (200, b"application"))
            self.assertEqual(forward.call_count, 1)
            self.assertEqual(forward.call_args.args[2], "/health/ready")
            self.assertEqual(forward.call_args.args[3]["Authorization"], "Bearer application-token")

    def test_settings_and_trust_are_instance_local(self):
        first_env = {"ACTIVE_TARGET_URL":"http://first.invalid", "PORT":"18080"}
        second_env = {"ACTIVE_TARGET_URL":"http://second.invalid"}
        with patch.dict(os.environ, {"ACTIVE_TARGET_URL":"http://ambient.invalid"}):
            with self.assertRaises(config.RouterConfigurationError):
                config.RouterSettings.from_environment({})
        for port in ("invalid-secret", "0", "65536"):
            with self.assertRaises(config.RouterConfigurationError) as caught:
                config.RouterSettings.from_environment({**first_env, "PORT":port})
            self.assertIsNone(caught.exception.__cause__)
            self.assertIsNone(caught.exception.__context__)
            self.assertNotIn("secret", str(caught.exception))
        other = fixture("b")
        with running(self, self.fixture, first_env) as first, running(self, other, second_env) as second, \
                patch.object(router, "forward", return_value=(200, b"ok", "text/plain")) as forward:
            first_env["ACTIVE_TARGET_URL"] = "http://changed.invalid"
            with patch.dict(os.environ, {"ACTIVE_TARGET_URL":"http://ambient.invalid"}):
                request(first, "/first")
                request(second, "/second")
            self.assertEqual([call.args[0].active_target_url for call in forward.call_args_list],
                             ["http://first.invalid", "http://second.invalid"])
            self.assertNotIn("first.invalid", repr(forward.call_args_list[0].args[0]))
            self.assertEqual(request(second, "/__control/health/liveness", token(other))[0], 200)
            self.assertNotEqual(request(second, "/__control/health/liveness", token(self.fixture))[0], 200)
            self.assertEqual(forward.call_count, 2)
