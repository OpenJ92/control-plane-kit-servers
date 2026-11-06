"""First #190 product laws; no live backend or credentials."""
from dataclasses import replace
import importlib
import unittest

import control_plane_kit_core as core
from control_plane_kit_core.configuration import ConfigurationFileMode, ConfigurationMediaType


class ManagedWebsiteTests(unittest.TestCase):
    def module(self, name):
        return importlib.import_module("control_plane_kit_servers_website_server." + name)

    def test_one_node_runtime_declares_distinct_visitor_and_management_sockets(self):
        contract = self.module("managed").declared_runtime_contract()
        self.assertEqual({(item.provider_socket, item.container_port) for item in contract.provider_ports},
                         {("http", 8080), ("control", 8000)})
        self.assertEqual(len(contract.control_surfaces), 1)

    def test_source_contract_preserves_concrete_public_artifact_and_provenance(self):
        import json
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloudflared_connector" / "tests"))
        from managed_control_fixtures import fixture
        managed = self.module("managed")
        configuration = replace(fixture().config, declaration=managed.control_declaration())
        artifact = managed.control_configuration_artifact(configuration)
        artifact = replace(artifact, content=json.dumps(json.loads(artifact.content), indent=2),
            source_digest="a" * 64)
        contract = managed.source_runtime_contract(artifact)
        self.assertEqual(contract.configuration_requirements, ())
        self.assertIs(contract.configuration_artifacts[0], artifact)
        self.assertEqual(replace(contract, configuration_artifacts=(),
            configuration_requirements=managed.declared_runtime_contract().configuration_requirements),
            managed.declared_runtime_contract())

    def test_source_contract_refuses_wrong_slot_or_malformed_receiver_without_echo(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloudflared_connector" / "tests"))
        from managed_control_fixtures import fixture
        managed = self.module("managed")
        artifact = managed.control_configuration_artifact(replace(fixture().config,
            declaration=managed.control_declaration()))
        for changed in (None, replace(artifact, artifact_id="foreign-control"),
                replace(artifact, target_path="/etc/cpk/foreign.json"),
                replace(artifact, media_type=ConfigurationMediaType.TEXT),
                replace(artifact, file_mode=ConfigurationFileMode.OWNER_READ_ONLY),
                replace(artifact, content='{"unexpected":"sentinel-private-content"}')):
            with self.subTest(artifact=changed), self.assertRaises(ValueError) as raised:
                managed.source_runtime_contract(changed)
            self.assertEqual(str(raised.exception), "Website control configuration is invalid")
            self.assertIsNone(raised.exception.__context__)

    def test_child_exit_and_stop_never_reuse_readiness(self):
        process = self.module("process")
        class Child:
            code = None
            def poll(self):
                return self.code
        child = Child()
        health = process.WebsiteHealth(child)
        self.assertEqual(health.liveness(), core.NodeHealthReadOutcome.HEALTHY)
        self.assertEqual(health.readiness(), core.NodeHealthReadOutcome.UNKNOWN)
        child.code = 1
        self.assertEqual(health.readiness(), core.NodeHealthReadOutcome.UNHEALTHY)
        child.code = None
        self.assertEqual(health.readiness(), core.NodeHealthReadOutcome.UNHEALTHY)
        replacement = process.WebsiteHealth(Child())
        self.assertEqual(replacement.readiness(), core.NodeHealthReadOutcome.UNKNOWN)
        replacement.stop()
        self.assertEqual(replacement.liveness(), core.NodeHealthReadOutcome.UNHEALTHY)

    def test_child_environment_excludes_control_material_and_arbitrary_node_options(self):
        env = self.module("process").node_environment({
            "CPK_WEB_UPSTREAM": "https://child.example.invalid", "PORT": "8080",
            "CPK_WRAPPER_CONFIGURATION_FILE": "/private/control.json",
            "NODE_OPTIONS": "--inspect=0.0.0.0", "PRIVATE": "never-forward",
        })
        self.assertEqual(env, {"NODE_ENV": "production", "PORT": "8080",
                              "CPK_WEB_UPSTREAM": "https://child.example.invalid"})

    def test_wrong_port_refuses_instead_of_colliding_with_control(self):
        with self.assertRaises(ValueError):
            self.module("process").node_environment({
                "CPK_WEB_UPSTREAM": "https://child.example.invalid", "PORT": "8000"})

    def test_sdk_protects_health_and_unknown_becomes_unhealthy_on_stop(self):
        import json
        import sys
        import time
        from pathlib import Path
        from threading import Thread
        # Reuse the existing SDK test authority fixture, never production keys.
        fixture_path = Path(__file__).resolve().parents[2] / "cloudflared_connector" / "tests"
        sys.path.insert(0, str(fixture_path))
        from managed_control_fixtures import fixture, token, request
        managed = self.module("managed")
        process = self.module("process")
        class Child:
            def poll(self):
                return None
        health = process.WebsiteHealth(Child())
        value = fixture()
        host = managed.create_control_server(value.config, health, address=("127.0.0.1", 0), clock=lambda:150)
        serving = Thread(target=host.serve_forever, kwargs={"poll_interval":0.01}, daemon=True)
        serving.start()
        try:
            deadline = time.monotonic() + 2
            while not host.cpk_is_serving:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            path = "/__control/health/readiness"
            for credential in (None, token(value, static=True)):
                self.assertEqual(request(host, path, credential)[0], 401)
            status, body, _ = request(host, path, token(value))
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["outcome"], "unknown")
            health.stop()
            status, body, _ = request(host, path, token(value))
            self.assertEqual(json.loads(body)["outcome"], "unhealthy")
        finally:
            host.shutdown()
            host.server_close()
            serving.join(2)
            self.assertFalse(serving.is_alive())

    def test_management_refusal_prevents_any_node_launch(self):
        import sys
        from pathlib import Path
        from unittest.mock import patch
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloudflared_connector" / "tests"))
        from managed_control_fixtures import fixture
        process = self.module("process")
        with patch.object(process.subprocess, "Popen") as spawn, \
                patch.object(process, "create_control_server", side_effect=OSError("synthetic bind refusal")):
            result = process.run(fixture().config, {"CPK_WEB_UPSTREAM":"https://child.example.invalid"})
        self.assertEqual(result, 1)
        spawn.assert_not_called()

    def test_management_holder_attaches_one_process_generation(self):
        class Child:
            def poll(self):
                return None
        health = self.module("process").WebsiteHealth()
        self.assertEqual(health.liveness().value, "unknown")
        health.attach(Child())
        self.assertEqual(health.liveness().value, "healthy")
        with self.assertRaises(ValueError):
            health.attach(Child())
        health.stop()
        with self.assertRaises(ValueError):
            health.attach(Child())

    def test_requested_stop_preserves_child_drain_failure_before_timeout(self):
        import signal
        import sys
        from pathlib import Path
        from threading import Event
        from unittest.mock import Mock, patch
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloudflared_connector" / "tests"))
        from managed_control_fixtures import fixture
        process = self.module("process")
        for code in (0, 1):
            with self.subTest(child_exit=code):
                handlers = {}
                released = Event()
                child = Mock(pid=1234)
                child.poll.return_value = None
                child.wait.return_value = code
                host = Mock()
                host.serve_forever.side_effect = lambda **_kwargs: released.wait(2)
                host.shutdown.side_effect = released.set
                def spawn(*_args, **_kwargs):
                    handlers[signal.SIGTERM](signal.SIGTERM, None)
                    return child
                def register(signum, handler):
                    handlers[signum] = handler
                with patch.object(process.signal, "signal", side_effect=register), \
                        patch.object(process.subprocess, "Popen", side_effect=spawn), \
                        patch.object(process, "create_control_server", return_value=host), \
                        patch.object(process.os, "killpg"), \
                        patch.object(process.os, "set_blocking"), \
                        patch.object(process.os, "read", return_value=b""):
                    result = process.run(fixture().config, {"CPK_WEB_UPSTREAM":"https://child.example.invalid"})
                self.assertEqual(result, code)
                child.wait.assert_called_once_with(timeout=8)
