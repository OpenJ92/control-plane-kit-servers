"""First #190 product laws; no live backend or credentials."""
import importlib
import unittest

import control_plane_kit_core as core


class ManagedWebsiteTests(unittest.TestCase):
    def module(self, name):
        return importlib.import_module("control_plane_kit_servers_website_server." + name)

    def test_one_node_runtime_declares_distinct_visitor_and_management_sockets(self):
        contract = self.module("managed").declared_runtime_contract()
        self.assertEqual({(item.provider_socket, item.container_port) for item in contract.provider_ports},
                         {("http", 8080), ("control", 8000)})
        self.assertEqual(len(contract.control_surfaces), 1)

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
