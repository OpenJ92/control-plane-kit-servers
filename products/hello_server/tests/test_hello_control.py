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
from control_plane_kit_servers_hello_server import configuration as config
from control_plane_kit_servers_hello_server import dependencies as deps
from control_plane_kit_servers_hello_server import server as hello
from hello_control_fixtures import fixture, running, request, token


class HelloControlTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture()
        self.config = self.fixture.config
        self.artifact = config.hello_control_configuration_artifact(self.config)

    def rejected(self, action):
        with self.assertRaises(config.HelloConfigurationError) as caught:
            action()
        self.assertEqual(str(caught.exception), "Hello control configuration is invalid")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(vars(caught.exception), {})

    def test_configuration_artifact_and_source_contract_are_real_values(self):
        self.assertEqual(config.decode_hello_control_configuration(self.artifact.content.encode()), self.config)
        self.assertEqual(ConfigurationArtifact.from_descriptor(self.artifact.descriptor()), self.artifact)
        self.assertEqual(self.artifact.target_path, "/etc/cpk/hello/control.json")
        self.assertEqual(self.artifact.file_mode.value, "0444")
        contract = config.hello_source_runtime_contract(self.artifact)
        self.assertEqual(ProductRuntimeContractCodec().decode(contract.descriptor()), contract)
        self.assertEqual(contract.control_surfaces, (self.config.declaration.surface,))
        self.assertEqual(contract.provider_ports[0].container_port, 8000)
        self.assertEqual(contract.configuration_artifacts, (self.artifact,))
        self.assertIn("node-controllable", [c.value for c in contract.capabilities])
        descriptor = Path(__file__).resolve().parents[1] / "product.cpk.json"
        old = ProductDescriptorCodec().decode_document(descriptor.read_bytes()).product
        self.assertEqual(old.identity.contract_revision, 2)
        self.assertEqual(old.runtime_contract.control_surfaces, ())
        self.assertEqual(old.runtime_contract.configuration_artifacts, ())
        self.assertNotIn("public_key", repr(self.config))
        result = subprocess.run([sys.executable, "-I", "-B", "-c",
            "import sys; import control_plane_kit_servers_hello_server.configuration; "
            "assert 'control_plane_kit_servers_hello_server.server' not in sys.modules"],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_closed_configuration_rejects_invalid_keys_identity_and_oversize(self):
        original = json.loads(self.artifact.content)
        raw_cases = [b"", b"\xff", b"{" + b" " * 65536,
                     b'{"profile":"hello-control-unconfigured.v1"}',
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
                self.rejected(lambda: config.decode_hello_control_configuration(raw))
        with patch.object(hello, "ThreadingHTTPServer") as listener:
            self.rejected(lambda: hello.create_hello_server(None, {}))
            listener.assert_not_called()

    def test_fixed_file_checks_opened_regularity_symlinks_and_exact_byte_boundary(self):
        raw = self.artifact.content.encode()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "control.json"
            with patch.object(config, "CONTROL_PATH", str(path)):
                self.rejected(config.read_hello_control_configuration)
                path.write_bytes(raw + b" " * (65536 - len(raw)))
                self.assertEqual(config.read_hello_control_configuration(), self.config)
                with path.open("ab") as stream:
                    stream.write(b" ")
                self.rejected(config.read_hello_control_configuration)
                path.unlink()
                target = Path(directory) / "target"
                target.write_bytes(raw)
                path.symlink_to(target)
                self.rejected(config.read_hello_control_configuration)
                path.unlink()
                path.mkdir()
                self.rejected(config.read_hello_control_configuration)
                path.rmdir()
                os.mkfifo(path)
                self.rejected(config.read_hello_control_configuration)
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
                    self.assertEqual(config.read_hello_control_configuration(), self.config)
                self.rejected(config.read_hello_control_configuration)

    def test_passive_installation_bind_failure_and_production_port_policy(self):
        captured = []
        real = hello.ThreadingHTTPServer
        def create(*args, **kwargs):
            host = real(*args, **kwargs)
            captured.append(host)
            self.assertEqual(host.socket.getsockname()[1], 0)
            return host
        for failure in ("install_hello_control", "server_bind", "server_activate"):
            with self.subTest(stage=failure), patch.object(hello, "ThreadingHTTPServer", side_effect=create):
                owner = hello if failure == "install_hello_control" else real
                with patch.object(owner, failure, side_effect=RuntimeError("test startup failure")):
                    with self.assertRaises(RuntimeError):
                        hello.create_hello_server(self.config, {}, address=("127.0.0.1", 0))
                self.assertEqual(captured[-1].socket.fileno(), -1)
        for port in ("8001", "0", "invalid"):
            with patch.dict(os.environ, {"HELLO_PORT":port}), patch.object(hello, "ThreadingHTTPServer") as listener:
                with self.assertRaises(config.HelloConfigurationError):
                    hello.main()
                listener.assert_not_called()
        with patch.dict(os.environ, {"HELLO_PORT":"8000", "HELLO_COLOR":"blue"}), \
                patch.object(hello, "read_hello_control_configuration", return_value=self.config), \
                patch.object(hello, "create_hello_server") as create_host:
            create_host.return_value.serve_forever.side_effect = KeyboardInterrupt
            with self.assertRaises(KeyboardInterrupt):
                hello.main()
            self.assertEqual(create_host.call_args.kwargs["address"], ("0.0.0.0", 8000))
            create_host.return_value.server_close.assert_called_once()

    def test_signed_static_and_health_reads_admit_before_any_product_checks(self):
        environment = {"HELLO_DEPENDENCIES_JSON": '[{"name":"orders"}]',
                       "HELLO_HTTP_ORDERS_URL":"http://private", "HELLO_DATABASE_ORDERS_URL":"postgresql://private"}
        with patch.object(deps, "_check_http", return_value=[]) as http, \
                patch.object(deps, "_check_postgres", return_value=[]) as postgres, \
                running(self, self.fixture, environment) as host:
            for changes in (
                {"target":replace(self.config.target, node_id=core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.NODE,"other"))},
                {"runtime_id":core.NodeControlGraphReference(core.NodeControlGraphReferenceRole.RUNTIME,"other")},
                {"declaration_identity":core.WorkloadNodeControlSurfaceDeclarationIdentity("0" * 64)},
            ):
                self.assertNotEqual(request(host, "/__control/health/readiness", token(self.fixture, request_changes=changes))[0], 200)
            self.assertNotEqual(request(host, "/__control/health/readiness", "invalid")[0], 200)
            self.assertNotEqual(request(host, "/__control/health/readiness", token(self.fixture, static=True))[0], 200)
            self.assertNotEqual(request(host, "/__control/variables/x", token(self.fixture), "POST")[0], 200)
            http.assert_not_called()
            postgres.assert_not_called()
            self.assertEqual(host.hello_observations.payload()["count"], 0)
            static = request(host, "/__control/capabilities", token(self.fixture, static=True))
            self.assertEqual(static[0], 200)
            self.assertEqual(json.loads(static[1])["declaration"], self.config.declaration.descriptor())
            http.assert_not_called()
            status, body, headers = request(host, "/__control/health/readiness", token(self.fixture))
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["outcome"], "healthy")
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual((http.call_count, postgres.call_count), (1,1))
            http.side_effect = RuntimeError("private-url-and-key")
            status, body, _ = request(host, "/__control/health/readiness", token(self.fixture))
            self.assertEqual(status, 500)
            self.assertNotIn(b"private", body)
            self.assertEqual(request(host, "/health/ready")[:2], (500, b"dependency observation failed\n"))

    def test_instances_keep_keys_application_and_dependency_snapshots_separate(self):
        other = fixture("b")
        first_env = {"HELLO_MESSAGE":"first", "HELLO_DEPENDENCIES_JSON":'[{"name":"orders"}]'}
        with running(self, self.fixture, first_env) as first, running(self, other, {"HELLO_MESSAGE":"second"}) as second:
            first_env["HELLO_MESSAGE"] = "changed"
            first_env["HELLO_HTTP_ORDERS_URL"] = "http://injected"
            with patch.dict(os.environ, {"HELLO_MESSAGE":"global", "HELLO_DEPENDENCIES_JSON":"invalid"}):
                self.assertIn(b"first", request(first, "/")[1])
                self.assertIn(b"second", request(second, "/")[1])
                self.assertEqual(request(first, "/health/ready")[0], 503)
                self.assertEqual(request(second, "/health/ready")[:2], (200, b"ready\n"))
                self.assertEqual(json.loads(request(first, "/__control/health/readiness", token(self.fixture))[1])["outcome"], "unhealthy")
                self.assertEqual(request(second, "/__control/health/readiness", token(other))[0], 200)
                self.assertNotEqual(request(second, "/__control/health/readiness", token(self.fixture))[0], 200)
                self.assertEqual(request(first, "/missing")[:2], (404,b"not found\n"))
            self.assertEqual(first.hello_observations.payload()["count"], 1)
            self.assertEqual(second.hello_observations.payload()["count"], 1)
            with self.assertRaises(TypeError):
                first.hello_settings.dependencies.environ["HELLO_HTTP_ORDERS_URL"] = "changed"
