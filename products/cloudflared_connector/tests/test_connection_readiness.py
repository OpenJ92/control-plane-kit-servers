from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
import io
import json
import os
import socket
import threading
import time
import unittest
from unittest.mock import patch

from control_plane_kit_servers_cloudflared_connector import readiness


CONNECTOR = "77a0325c-ff03-4be4-8064-d940252751c3"


def native_body(status=200, count=2, **changes):
    value = {"status": status, "readyConnections": count, "connectorId": CONNECTOR}
    value.update(changes)
    return json.dumps(value).encode()


def response(body, status=200, headers=b""):
    return (
        f"HTTP/1.1 {status} Native\r\nContent-Length: {len(body)}\r\n".encode()
        + headers + b"\r\n" + body
    )


@contextmanager
def native_server(payload, *, delay=0, byte_delay=0):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 20241))
    listener.listen(1)
    listener.settimeout(0.2)
    requests = []
    errors = []
    stopped = threading.Event()

    def serve():
        try:
            while not stopped.is_set():
                try:
                    connection, _ = listener.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return
            with connection:
                connection.settimeout(4)
                requests.append(connection.recv(4096))
                time.sleep(delay)
                if byte_delay:
                    header, _, body = payload.partition(b"\r\n\r\n")
                    connection.sendall(header + b"\r\n\r\n")
                    for byte in body:
                        connection.sendall(bytes([byte]))
                        time.sleep(byte_delay)
                else:
                    connection.sendall(payload)
        except (BrokenPipeError, ConnectionResetError):
            return  # Reader has deliberately closed at its deadline/bound.
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=serve)
    worker.start()
    try:
        yield requests
    finally:
        stopped.set()
        worker.join(5)
        listener.close()
        if worker.is_alive():
            raise AssertionError("native fixture did not terminate")
        if errors:
            raise AssertionError("native fixture failed") from errors[0]


class ConnectionClassificationTests(unittest.TestCase):
    def decoded(self, status, body):
        line = readiness.classify_response(status, body).encode()
        self.assertLessEqual(len(line.encode()), 256)
        self.assertNotIn("SECRET_SENTINEL", line)
        return json.loads(line)

    def test_native_connection_and_zero_have_distinct_truth(self):
        for status, count, outcome in ((200, 2, "connected"), (503, 0, "disconnected")):
            with self.subTest(outcome=outcome):
                self.assertEqual(self.decoded(status, native_body(status, count)), {
                    "schema": "cpk.cloudflared.connection/v1", "outcome": outcome,
                    "readyConnections": count, "connectorId": CONNECTOR,
                })

    def test_inconsistent_native_status_and_counts_are_unknown(self):
        cases = [(200, native_body(503, 0)), (503, native_body(200, 2)),
                 (200, native_body(200, 0)), (503, native_body(503, 1)),
                 (302, native_body()), (500, native_body()),
                 (200, native_body(count=True)), (200, native_body(count=-1)),
                 (200, native_body(count=1.5)), (200, native_body(count=2**64)),
                 (200, native_body(status=True))]
        for status, body in cases:
            with self.subTest(status=status, body=body):
                result = self.decoded(status, body)
                self.assertEqual(result["outcome"], "unknown")
                self.assertEqual(set(result), {"schema", "outcome", "reason"})

    def test_uint64_boundary_and_uuid_are_strict(self):
        self.assertEqual(self.decoded(200, native_body(count=2**64-1))["outcome"], "connected")
        for identity in ("00000000-0000-0000-0000-000000000000", CONNECTOR.upper(),
                         "SECRET_SENTINEL", None, 4):
            with self.subTest(identity=identity):
                self.assertEqual(self.decoded(200, native_body(connectorId=identity))["outcome"], "unknown")

    def test_malformed_duplicate_unknown_or_oversized_fields_are_unknown(self):
        cases = [b"SECRET_SENTINEL", b"[]", b"null", b"\xff", b"{}",
                 native_body(extra="SECRET_SENTINEL"), b"x" * 1025,
                 native_body()[:-1] + b',"status":200}',
                 b'{"status":200,"readyConnections":NaN,"connectorId":"' + CONNECTOR.encode() + b'"}']
        for body in cases:
            with self.subTest(body=body[:40]):
                self.assertEqual(self.decoded(200, body)["outcome"], "unknown")


class ConnectionTransportTests(unittest.TestCase):
    def test_exact_fixed_request_and_proxy_environment_ignored(self):
        with native_server(response(native_body())) as requests:
            with patch.dict(os.environ, {"HTTP_PROXY": "http://SECRET_SENTINEL:1",
                                         "ALL_PROXY": "http://SECRET_SENTINEL:1",
                                         "NO_PROXY": ""}):
                sample = readiness.read_connection()
        self.assertEqual(json.loads(sample.encode())["outcome"], "connected")
        self.assertEqual(requests, [b"GET /ready HTTP/1.1\r\nHost: 127.0.0.1:20241\r\nConnection: close\r\n\r\n"])

    def test_zero_connections_are_distinct_from_refused_transport(self):
        with native_server(response(native_body(503, 0), 503)):
            sample = readiness.read_connection()
        self.assertEqual(json.loads(sample.encode())["outcome"], "disconnected")
        # The same fixed port is now closed; refusal cannot mean disconnected.
        self.assertEqual(json.loads(readiness.read_connection().encode())["outcome"], "unknown")

    def test_redirect_truncation_and_transfer_ambiguity_are_unknown(self):
        for payload in (response(b"", 302, b"Location: http://SECRET_SENTINEL/\r\n"),
                        response(native_body())[:-10],
                        response(native_body(), headers=b"Transfer-Encoding: chunked\r\n"),
                        response(native_body(), headers=b"Content-Length: 1\r\n"),
                        response(native_body(), headers=b"Content-Encoding: gzip\r\n"),
                        b"HTTP/1.1 200 OK\r\n\r\n" + native_body()):
            with self.subTest(payload=payload[:35]), native_server(payload):
                encoded = readiness.read_connection().encode()
                self.assertEqual(json.loads(encoded)["outcome"], "unknown")
                self.assertNotIn("SECRET_SENTINEL", encoded)

    def test_header_and_body_limits_reject_before_diagnostics_escape(self):
        for payload in (response(b"SECRET_SENTINEL" * 100),
                        response(native_body(), headers=b"X-Huge: " + b"a" * 8192 + b"\r\n")):
            with self.subTest(size=len(payload)), native_server(payload):
                encoded = readiness.read_connection().encode()
                self.assertEqual(json.loads(encoded)["outcome"], "unknown")
                self.assertLessEqual(len(encoded.encode()), 256)
                self.assertNotIn("SECRET_SENTINEL", encoded)

    def test_slow_headers_and_body_share_total_deadline(self):
        for payload, delay, byte_delay in (
            (response(native_body()), 2.4, 0),
            (response(native_body()), 0, 0.04),
        ):
            with self.subTest(delay=delay), native_server(payload, delay=delay, byte_delay=byte_delay):
                started = time.monotonic()
                encoded = readiness.read_connection().encode()
                elapsed = time.monotonic() - started
                self.assertEqual(json.loads(encoded)["outcome"], "unknown")
                self.assertLess(elapsed, 2.8)

    def test_command_outputs_one_bounded_line_and_truthful_exit(self):
        for status, count, exit_code in ((200, 1, 0), (503, 0, 1)):
            with self.subTest(status=status), native_server(response(native_body(status, count), status)):
                output = io.StringIO()
                with redirect_stdout(output):
                    observed = readiness.main()
                self.assertEqual(observed, exit_code)
                self.assertEqual(len(output.getvalue().splitlines()), 1)
                self.assertLessEqual(len(output.getvalue().encode()), 256)


if __name__ == "__main__":
    unittest.main()
