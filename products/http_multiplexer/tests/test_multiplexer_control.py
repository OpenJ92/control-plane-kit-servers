from dataclasses import replace
import json
import importlib
from io import BytesIO
from urllib.error import HTTPError
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
from control_plane_kit_servers_http_multiplexer import configuration as config
from control_plane_kit_servers_http_multiplexer import server as multiplexer
from multiplexer_control_fixtures import fixture, running, request, token


class MultiplexerControlTests(unittest.TestCase):
    def setUp(self):
        # Existing descriptor tests deliberately evict process modules between cases.
        global config, multiplexer
        config = importlib.import_module("control_plane_kit_servers_http_multiplexer.configuration")
        multiplexer = importlib.import_module("control_plane_kit_servers_http_multiplexer.server")
        self.fixture = fixture()
        self.config = self.fixture.config
        self.artifact = config.multiplexer_control_configuration_artifact(self.config)

    def rejected(self, action):
        with self.assertRaises(config.MultiplexerConfigurationError) as caught:
            action()
        self.assertEqual(str(caught.exception), "Multiplexer control configuration is invalid")
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(vars(caught.exception), {})

    def test_configuration_artifact_and_source_contract_are_real_values(self):
        self.assertEqual(config.decode_multiplexer_control_configuration(self.artifact.content.encode()), self.config)
        self.assertEqual(ConfigurationArtifact.from_descriptor(self.artifact.descriptor()), self.artifact)
        self.assertEqual(self.artifact.target_path, "/etc/cpk/multiplexer/control.json")
        self.assertEqual(self.artifact.file_mode.value, "0444")
        contract = config.multiplexer_source_runtime_contract(self.artifact)
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
        for field in ("sockets", "provider_ports", "public_environment", "secret_deliveries",
                      "retained_data_mounts", "lifecycle"):
            self.assertEqual(getattr(contract, field), getattr(old.runtime_contract, field))
        self.assertNotIn("public_key", repr(self.config))
        result = subprocess.run([sys.executable, "-I", "-B", "-c",
            "import sys; import control_plane_kit_servers_http_multiplexer; import control_plane_kit_servers_http_multiplexer.configuration; "
            "assert 'control_plane_kit_servers_http_multiplexer.server' not in sys.modules"],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_closed_configuration_rejects_invalid_keys_identity_and_oversize(self):
        original = json.loads(self.artifact.content)
        raw_cases = [b"", b"\xff", b"{" + b" " * 65536,
                     b'{"profile":"multiplexer-control-unconfigured.v1"}',
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
                self.rejected(lambda: config.decode_multiplexer_control_configuration(raw))
        self.rejected(lambda: replace(self.config, health_keys=self.config.surface_keys))
        self.rejected(lambda: replace(self.config, runtime_id=core.NodeControlGraphReference(
            core.NodeControlGraphReferenceRole.NODE, "wrong-role")))
        self.rejected(lambda: config.multiplexer_control_configuration_artifact(None))
        self.rejected(lambda: config.multiplexer_source_runtime_contract(None))
        interrupted = KeyboardInterrupt()
        with patch.object(config.json, "loads", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt) as caught:
                config.decode_multiplexer_control_configuration(self.artifact.content.encode())
            self.assertIs(caught.exception, interrupted)
        with patch.object(multiplexer, "ThreadingHTTPServer") as listener:
            self.rejected(lambda: multiplexer.create_multiplexer_server(None, config.MultiplexerSettings("http://upstream.invalid")))
            listener.assert_not_called()

    def test_fixed_file_checks_opened_regularity_symlinks_and_exact_byte_boundary(self):
        raw = self.artifact.content.encode()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "control.json"
            with patch.object(config, "CONTROL_PATH", str(path)):
                self.rejected(config.read_multiplexer_control_configuration)
                path.write_bytes(raw + b" " * (65536 - len(raw)))
                self.assertEqual(config.read_multiplexer_control_configuration(), self.config)
                with path.open("ab") as stream:
                    stream.write(b" ")
                self.rejected(config.read_multiplexer_control_configuration)
                path.unlink()
                target = Path(directory) / "target"
                target.write_bytes(raw)
                path.symlink_to(target)
                self.rejected(config.read_multiplexer_control_configuration)
                path.unlink()
                path.mkdir()
                self.rejected(config.read_multiplexer_control_configuration)
                path.rmdir()
                os.mkfifo(path)
                self.rejected(config.read_multiplexer_control_configuration)
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
                    self.assertEqual(config.read_multiplexer_control_configuration(), self.config)
                self.rejected(config.read_multiplexer_control_configuration)

    def test_passive_installation_bind_failure_and_production_port_policy(self):
        captured = []
        real = multiplexer.ThreadingHTTPServer
        def create(*args, **kwargs):
            host = real(*args, **kwargs)
            captured.append(host)
            self.assertEqual(host.socket.getsockname()[1], 0)
            return host
        for failure in ("install_multiplexer_control", "server_bind", "server_activate"):
            with self.subTest(stage=failure), patch.object(multiplexer, "ThreadingHTTPServer", side_effect=create):
                owner = multiplexer if failure == "install_multiplexer_control" else real
                with patch.object(owner, failure, side_effect=RuntimeError("test startup failure")):
                    with self.assertRaises(RuntimeError):
                        multiplexer.create_multiplexer_server(self.config, config.MultiplexerSettings("http://upstream.invalid"), address=("127.0.0.1", 0))
                self.assertEqual(captured[-1].socket.fileno(), -1)
        for port in ("8001", "0", "invalid"):
            with patch.dict(os.environ, {"PORT":port, "MULTIPLEXER_PRIMARY_URL":"http://upstream.invalid"}), patch.object(multiplexer, "ThreadingHTTPServer") as listener:
                self.assertEqual(multiplexer.main(), 2)
                listener.assert_not_called()
        with patch.dict(os.environ, {"PORT":"8000", "MULTIPLEXER_PRIMARY_URL":"http://upstream.invalid"}), \
                patch.object(multiplexer, "read_multiplexer_control_configuration", return_value=self.config), \
                patch.object(multiplexer, "create_multiplexer_server") as create_host:
            create_host.return_value.serve_forever.side_effect = KeyboardInterrupt
            self.assertEqual(multiplexer.main(), 0)
            self.assertEqual(create_host.call_args.kwargs["address"], ("0.0.0.0", 8000))
            create_host.return_value.server_close.assert_called_once()

    def test_reserved_reads_and_denials_reach_neither_forwarding_lane(self):
        live = "/__control/health/liveness"
        environment = {"MULTIPLEXER_PRIMARY_URL":"http://primary.invalid",
                       "MULTIPLEXER_OBSERVER_A_URL":"http://observer-a.invalid",
                       "MULTIPLEXER_OBSERVER_B_URL":"http://observer-b.invalid"}
        with patch.object(multiplexer, "forward_primary", return_value=(201, b"primary", "text/plain")) as primary, \
                patch.object(multiplexer, "deliver_observers", return_value=()) as observers, \
                running(self, self.fixture, environment) as host:
            static = request(host, "/__control/capabilities", token(self.fixture, static=True))
            self.assertEqual(static[0], 200)
            self.assertEqual(json.loads(static[1])["declaration"], self.config.declaration.descriptor())
            status, body, headers = request(host, live, token(self.fixture))
            self.assertEqual(status, 200)
            observed = core.NodeHealthReadRequest(self.config.target, self.config.runtime_id,
                core.NodeHealthReadKind.LIVENESS, self.config.declaration.identity(), "health-request")
            result = core.NodeHealthReadResultCodec(observed, self.config.declaration).decode(json.loads(body))
            self.assertIs(result.outcome, core.NodeHealthReadOutcome.HEALTHY)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(self.config.declaration.surface.health_reads, (core.NodeHealthReadKind.LIVENESS,))
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
                                 (live, "PUT"), ("/%5f_control/health/liveness", "GET"),
                                 (live + "?unexpected=1", "GET")):
                self.assertNotEqual(request(host, path, token(self.fixture), method)[0], 200)
            primary.assert_not_called()
            observers.assert_not_called()
            self.assertEqual(request(host, "/health/live")[:2], (200, b"live\n"))
            primary.assert_not_called()
            observers.assert_not_called()
            self.assertEqual(request(host, "/health/ready", "application-token")[:2], (201, b"primary"))
            self.assertEqual((primary.call_count, observers.call_count), (1, 1))
            for lane in (primary, observers):
                self.assertEqual(lane.call_args.args[2], "/health/ready")
                self.assertEqual(lane.call_args.args[3]["Authorization"], "Bearer application-token")

    def test_primary_failure_skips_observers_and_observer_failure_preserves_primary(self):
        environment = {"MULTIPLEXER_PRIMARY_URL":"http://primary.invalid",
                       "MULTIPLEXER_OBSERVER_A_URL":"http://observer-a.invalid",
                       "MULTIPLEXER_OBSERVER_B_URL":"http://observer-b.invalid"}
        with running(self, self.fixture, environment) as host:
            primary_error = HTTPError("http://private.invalid", 409, "private", {}, BytesIO(b"private"))
            try:
                for failure in (primary_error, TimeoutError("private"), RuntimeError("upstream response too large")):
                    with self.subTest(kind=type(failure).__name__), \
                            patch.object(multiplexer, "_open", side_effect=failure) as opened, \
                            patch.object(multiplexer, "deliver_observers") as observers:
                        self.assertEqual(request(host, "/failure")[:2], (502, b"primary request failed\n"))
                        self.assertEqual(opened.call_count, 1)
                        observers.assert_not_called()
            finally:
                primary_error.close()
            # Actual deliver_observers catches the first failure and continues before
            # the handler returns the already selected primary response.
            calls = []
            def open_lane(url, method, headers, body, limit):
                calls.append((url, method, headers["Authorization"], headers["X-Test"], body, limit))
                if "observer-a" in url:
                    raise RuntimeError("token=private observer-location")
                if "observer-b" in url:
                    return 202, b"observer result", "application/observer"
                return 201, b"primary result", "application/primary"
            with patch.object(multiplexer, "_open", side_effect=open_lane):
                status, body, headers = request(host, "/path?q=1", "application-auth", "PATCH",
                                               body=b"payload", headers={"X-Test":"copied"})
            self.assertEqual((status, body, headers["content-type"]), (201, b"primary result", "application/primary"))
            self.assertEqual(calls, [
                ("http://primary.invalid/path?q=1", "PATCH", "Bearer application-auth", "copied", b"payload", 1048576),
                ("http://observer-a.invalid/path?q=1", "PATCH", "Bearer application-auth", "copied", b"payload", 16384),
                ("http://observer-b.invalid/path?q=1", "PATCH", "Bearer application-auth", "copied", b"payload", 16384),
            ])
        with running(self, self.fixture) as host, patch.object(multiplexer, "_open", return_value=(200,b"primary","text/plain")) as opened:
            self.assertEqual(request(host, "/without-observers")[:2], (200, b"primary"))
            self.assertEqual(opened.call_count, 1)

    def test_settings_and_trust_are_instance_local(self):
        first_env = {"MULTIPLEXER_PRIMARY_URL":"http://first.invalid", "PORT":"18082",
                     "MULTIPLEXER_OBSERVER_A_URL":"http://observer-first.invalid"}
        second_env = {"MULTIPLEXER_PRIMARY_URL":"http://second.invalid",
                      "MULTIPLEXER_OBSERVER_B_URL":"http://observer-second.invalid"}
        with patch.dict(os.environ, {"MULTIPLEXER_PRIMARY_URL":"http://ambient.invalid"}):
            with self.assertRaises(config.MultiplexerConfigurationError):
                config.MultiplexerSettings.from_environment({})
        for port in ("invalid-secret", "0", "65536"):
            with self.assertRaises(config.MultiplexerConfigurationError) as caught:
                config.MultiplexerSettings.from_environment({**first_env, "PORT":port})
            self.assertIsNone(caught.exception.__cause__)
            self.assertIsNone(caught.exception.__context__)
            self.assertNotIn("secret", str(caught.exception))
        for invalid_observers in (["http://mutable.invalid"], ("ftp://invalid",)):
            with self.assertRaises(config.MultiplexerConfigurationError):
                config.MultiplexerSettings("http://primary.invalid", invalid_observers)
        standalone = config.MultiplexerSettings("http://primary.invalid", ("http://a.invalid", "http://b.invalid", "http://c.invalid"), 18082)
        self.assertEqual(len(standalone.observer_urls), 3)
        other = fixture("b")
        with running(self, self.fixture, first_env) as first, running(self, other, second_env) as second, \
                patch.object(multiplexer, "forward_primary", return_value=(200,b"ok","text/plain")) as primary, \
                patch.object(multiplexer, "deliver_observers", return_value=()) as observers:
            first_env["MULTIPLEXER_PRIMARY_URL"] = "http://changed.invalid"
            first_env["MULTIPLEXER_OBSERVER_A_URL"] = "http://changed-observer.invalid"
            with patch.dict(os.environ, {"MULTIPLEXER_PRIMARY_URL":"http://ambient.invalid"}):
                request(first, "/first")
                request(second, "/second")
            self.assertEqual([call.args[0].primary_url for call in primary.call_args_list],
                             ["http://first.invalid", "http://second.invalid"])
            self.assertEqual([call.args[0].observer_urls for call in observers.call_args_list],
                             [("http://observer-first.invalid",), ("http://observer-second.invalid",)])
            self.assertNotIn("first.invalid", repr(primary.call_args_list[0].args[0]))
            self.assertEqual(request(second, "/__control/health/liveness", token(other))[0], 200)
            self.assertNotEqual(request(second, "/__control/health/liveness", token(self.fixture))[0], 200)
            self.assertEqual((primary.call_count, observers.call_count), (2, 2))

    def test_open_preserves_per_lane_bounds_timeout_and_no_redirects(self):
        with patch.object(multiplexer.request, "build_opener") as build:
            opened = build.return_value.open
            response = opened.return_value.__enter__.return_value
            response.status = 201
            response.headers = {"content-type":"application/test"}
            for limit in (multiplexer.MAX_RESPONSE_BYTES, multiplexer.MAX_OBSERVER_RESPONSE_BYTES):
                with self.subTest(limit=limit):
                    response.read.reset_mock()
                    response.read.return_value = b"x" * limit
                    result = multiplexer._open("http://primary.invalid/path?q=1", "POST", {
                        "Authorization":"application-auth", "Host":"omit", "Connection":"omit",
                        "Content-Length":"100", "X-Test":"keep"}, b"payload", limit)
                    self.assertEqual((result[0], len(result[1]), result[2]), (201, limit, "application/test"))
                    response.read.assert_called_once_with(limit + 1)
                    self.assertEqual(opened.call_args.kwargs, {"timeout":5.0})
                    outbound = opened.call_args.args[0]
                    self.assertEqual((outbound.full_url, outbound.method, outbound.data),
                                     ("http://primary.invalid/path?q=1", "POST", b"payload"))
                    self.assertEqual({key.lower(): value for key, value in outbound.header_items()},
                                     {"authorization":"application-auth", "x-test":"keep"})
                    response.read.return_value = b"x" * (limit + 1)
                    with self.assertRaisesRegex(RuntimeError, "upstream response too large"):
                        multiplexer._open("http://primary.invalid", "GET", {}, b"", limit)
        with self.assertRaises(HTTPError) as caught:
            multiplexer.NoRedirects().redirect_request(
                multiplexer.request.Request("http://primary.invalid"), None, 302, "moved", {}, "http://elsewhere.invalid")
        self.assertEqual(caught.exception.code, 302)
