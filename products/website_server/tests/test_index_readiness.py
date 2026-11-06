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

    def test_chunked_content_length_contradiction_is_refused(self):
        probe = importlib.import_module("control_plane_kit_servers_website_server.index_probe")
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type",probe.MIME)
                self.send_header("Content-Length","4")
                self.send_header("Transfer-Encoding","chunked")
                self.end_headers()
                try:
                    self.wfile.write(b"4\r\npage\r\n0\r\n\r\n")
                except OSError:
                    return
            def log_message(self,*_args):
                return
        host = ThreadingHTTPServer(("127.0.0.1",8080),Handler)
        host.daemon_threads = True
        worker = Thread(target=host.serve_forever,daemon=True)
        worker.start()
        try:
            self.assertEqual(probe.read_index(probe.IndexExpectation(4,sha256(b"page").hexdigest())).value,"unhealthy")
        finally:
            host.shutdown()
            host.server_close()
            worker.join(2)

    def test_close_trickle_has_absolute_deadline_and_releases_probe_slot(self):
        process = importlib.import_module("control_plane_kit_servers_website_server.process")
        probe = importlib.import_module("control_plane_kit_servers_website_server.index_probe")
        class Child:
            def poll(self):
                return None
        class Handler(BaseHTTPRequestHandler):
            calls = 0
            protocol_version = "HTTP/1.1"
            def do_GET(self):
                Handler.calls += 1
                slow = Handler.calls == 1
                self.send_response(200)
                self.send_header("Content-Type",probe.MIME)
                self.send_header("Content-Length","4")
                self.send_header("Connection","close")
                self.end_headers()
                try:
                    for byte in b"page":
                        if slow:
                            time.sleep(0.8)
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                except OSError:
                    return
            def log_message(self,*_args):
                return
        child = Child()
        health = process.WebsiteHealth(child,expectation=probe.IndexExpectation(4,sha256(b"page").hexdigest()))
        health.listening(child)
        host = ThreadingHTTPServer(("127.0.0.1",8080),Handler)
        host.daemon_threads = True
        worker = Thread(target=host.serve_forever,daemon=True)
        worker.start()
        try:
            started = time.monotonic()
            self.assertEqual(health.readiness().value,"unknown")
            self.assertLess(time.monotonic()-started,1.75)
            self.assertEqual(health.readiness().value,"healthy")
        finally:
            host.shutdown()
            host.server_close()
            worker.join(2)

    def test_unexpected_fifo_cannot_block_startup_expectation_read(self):
        import os
        from pathlib import Path
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"unexpected-fifo"
            os.mkfifo(path)
            result = subprocess.run(
                [sys.executable,"-c",
                 "import sys;from control_plane_kit_servers_website_server import index_probe;"
                 "index_probe.EXPECTATION_PATH=sys.argv[1];print(index_probe.load_expectation() is None)",str(path)],
                capture_output=True,timeout=2,check=True)
            self.assertEqual(result.stdout.strip(),b"True")
