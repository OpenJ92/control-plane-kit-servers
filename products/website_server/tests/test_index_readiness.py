"""Local expected-page readiness laws, independent of public route/upstream."""
from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
from threading import Thread
import time
import unittest


@contextmanager
def page_server(body, status=200, delay=0):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        calls = 0
        def do_GET(self):
            Handler.calls += 1
            time.sleep(delay)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                return
        def log_message(self, *_args):
            return
    host = ThreadingHTTPServer(("127.0.0.1",8080), Handler)
    host.daemon_threads = True
    thread = Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        yield Handler
    finally:
        host.shutdown()
        host.server_close()
        thread.join(2)


class IndexReadinessTests(unittest.TestCase):
    def test_identical_foreign_page_is_ineligible_until_owned_listen_signal(self):
        process = importlib.import_module("control_plane_kit_servers_website_server.process")
        probe = importlib.import_module("control_plane_kit_servers_website_server.index_probe")
        class Child:
            code = None
            def poll(self):
                return self.code
        child = Child()
        body = b"selected page"
        health = process.WebsiteHealth(child, expectation=probe.IndexExpectation(len(body), sha256(body).hexdigest()))
        with page_server(body) as server:
            self.assertEqual(health.readiness().value,"unknown")
            self.assertEqual(server.calls,0)
            health.listening(child)
            self.assertEqual(health.readiness().value,"healthy")
            child.code = 1
            self.assertEqual(health.readiness().value,"unhealthy")
            child.code = None
            self.assertEqual(health.readiness().value,"unhealthy")

    def test_mismatch_redirect_and_deadline_never_report_healthy(self):
        probe = importlib.import_module("control_plane_kit_servers_website_server.index_probe")
        body = b"selected page"
        expected = probe.IndexExpectation(len(body),sha256(body).hexdigest())
        for actual, status, delay, outcome in (
            (b"wrong page",200,0,"unhealthy"), (body,302,0,"unhealthy"),
            (body,200,2,"unknown")):
            with self.subTest(status=status,delay=delay), page_server(actual,status,delay) as server:
                self.assertEqual(probe.read_index(expected).value,outcome)
                self.assertEqual(server.calls,1)

    def test_expected_file_must_be_bounded_readonly_regular_build_material(self):
        import json
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        probe = importlib.import_module("control_plane_kit_servers_website_server.index_probe")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expected.json"
            with patch.object(probe, "EXPECTATION_PATH", str(path)):
                self.assertIsNone(probe.load_expectation())
                value = {"schema":"cpk.website-index.v1","length":4,"sha256":sha256(b"page").hexdigest()}
                path.write_text(json.dumps(value))
                self.assertIsNone(probe.load_expectation())
                path.chmod(0o444)
                self.assertEqual(probe.load_expectation(),probe.IndexExpectation(4,sha256(b"page").hexdigest()))
                path.chmod(0o644)
                path.write_text("x" * 513)
                path.chmod(0o444)
                self.assertIsNone(probe.load_expectation())
                path.unlink()
                path.symlink_to(Path(directory) / "missing")
                self.assertIsNone(probe.load_expectation())

    def test_child_exit_overrides_a_late_matching_page(self):
        from threading import Event
        from unittest.mock import patch
        process = importlib.import_module("control_plane_kit_servers_website_server.process")
        probe = importlib.import_module("control_plane_kit_servers_website_server.index_probe")
        class Child:
            code = None
            def poll(self):
                return self.code
        child = Child()
        health = process.WebsiteHealth(child,expectation=probe.IndexExpectation(4,sha256(b"page").hexdigest()))
        health.listening(child)
        entered, release = Event(), Event()
        result = []
        def delayed(_expected):
            entered.set()
            self.assertTrue(release.wait(2))
            return process.core.NodeHealthReadOutcome.HEALTHY
        with patch.object(process,"read_index",side_effect=delayed):
            worker = Thread(target=lambda:result.append(health.readiness()))
            worker.start()
            self.assertTrue(entered.wait(1))
            child.code = 1
            release.set()
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertEqual(result,[process.core.NodeHealthReadOutcome.UNHEALTHY])
