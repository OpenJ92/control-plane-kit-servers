"""Bounded native connection evidence, independent of public ingress health."""

from dataclasses import dataclass
import json
import re
import socket
import sys
import time
from uuid import UUID


_SCHEMA = "cpk.cloudflared.connection/v1"
_BODY_LIMIT = 1024
_HEADER_LIMIT = 8192
_REQUEST = b"GET /ready HTTP/1.1\r\nHost: 127.0.0.1:20241\r\nConnection: close\r\n\r\n"


@dataclass(frozen=True)
class ConnectionSample:
    outcome: str
    reason: str | None = None
    ready_connections: int | None = None
    connector_id: str | None = None

    def encode(self) -> str:
        value = {"schema": _SCHEMA, "outcome": self.outcome}
        if self.reason is not None:
            value["reason"] = self.reason
        else:
            value["readyConnections"] = self.ready_connections
            value["connectorId"] = self.connector_id
        return json.dumps(value, separators=(",", ":"))


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate native field")
        value[key] = item
    return value


def classify_response(status: int, body: bytes) -> ConnectionSample:
    """Interpret only the pinned native readiness response, never diagnostics."""
    if type(body) is not bytes or len(body) > _BODY_LIMIT:
        return ConnectionSample("unknown", "response_too_large")
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object)
        if type(value) is not dict or set(value) != {"status", "readyConnections", "connectorId"}:
            raise ValueError("invalid native fields")
        count, identity = value["readyConnections"], value["connectorId"]
        if type(status) is not int or type(value["status"]) is not int or value["status"] != status:
            raise ValueError("inconsistent status")
        if type(count) is not int or not 0 <= count < 2**64:
            raise ValueError("invalid connection count")
        if type(identity) is not str:
            raise ValueError("invalid connector identity")
        parsed = UUID(identity)
        if parsed.int == 0 or str(parsed) != identity:
            raise ValueError("noncanonical connector identity")
        if status == 200 and count > 0:
            return ConnectionSample("connected", ready_connections=count, connector_id=identity)
        if status == 503 and count == 0:
            return ConnectionSample("disconnected", ready_connections=0, connector_id=identity)
    except (ValueError, UnicodeError, RecursionError):
        return ConnectionSample("unknown", "invalid_response")
    return ConnectionSample("unknown", "invalid_response")


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return remaining


def _receive(connection: socket.socket, deadline: float, limit: int) -> bytes:
    connection.settimeout(_remaining(deadline))
    return connection.recv(limit)


def _read_response(connection: socket.socket, deadline: float) -> ConnectionSample:
    # The fixed local Go response uses Content-Length. This is not a generic
    # HTTP client: redirects, transfer encoding and compression are unsupported.
    received = b""
    while b"\r\n\r\n" not in received:
        part = _receive(connection, deadline, min(1024, _HEADER_LIMIT + 1 - len(received)))
        if not part:
            return ConnectionSample("unknown", "invalid_http")
        received += part
        if b"\r\n\r\n" not in received and len(received) >= _HEADER_LIMIT:
            return ConnectionSample("unknown", "response_too_large")
    header, _, body = received.partition(b"\r\n\r\n")
    if len(header) + 4 > _HEADER_LIMIT:
        return ConnectionSample("unknown", "response_too_large")
    lines = header.split(b"\r\n")
    status_line = re.fullmatch(rb"HTTP/1\.[01] ([0-9]{3}) [\x20-\x7e]*", lines[0])
    if status_line is None:
        return ConnectionSample("unknown", "invalid_http")
    headers = {}
    for line in lines[1:]:
        name, separator, value = line.partition(b":")
        if not separator or re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) is None:
            return ConnectionSample("unknown", "invalid_http")
        name = name.lower()
        if name in headers or any(byte < 32 and byte != 9 or byte == 127 for byte in value):
            return ConnectionSample("unknown", "invalid_http")
        headers[name] = value.strip(b" \t")
    length = headers.get(b"content-length", b"")
    if (b"transfer-encoding" in headers or b"content-encoding" in headers
            or re.fullmatch(rb"[0-9]{1,10}", length) is None):
        return ConnectionSample("unknown", "invalid_http")
    size = int(length)
    if size > _BODY_LIMIT:
        return ConnectionSample("unknown", "response_too_large")
    if len(body) > size:
        return ConnectionSample("unknown", "invalid_http")
    while len(body) < size:
        part = _receive(connection, deadline, size - len(body))
        if not part:
            return ConnectionSample("unknown", "invalid_http")
        body += part
    _remaining(deadline)
    sample = classify_response(int(status_line.group(1)), body)
    _remaining(deadline)
    return sample


def read_connection() -> ConnectionSample:
    """One fixed loopback read within a single two-second monotonic budget."""
    deadline = time.monotonic() + 2.0
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(_remaining(deadline))
            connection.connect(("127.0.0.1", 20241))
            connection.settimeout(_remaining(deadline))
            connection.sendall(_REQUEST)
            return _read_response(connection, deadline)
    except TimeoutError:
        return ConnectionSample("unknown", "timeout")
    except OSError:
        return ConnectionSample("unknown", "transport_unavailable")


def main() -> int:
    sample = read_connection()
    print(sample.encode())
    return 0 if sample.outcome == "connected" else 1


if __name__ == "__main__":
    if len(sys.argv) != 1:
        print(ConnectionSample("unknown", "invalid_invocation").encode())
        raise SystemExit(1)
    raise SystemExit(main())
