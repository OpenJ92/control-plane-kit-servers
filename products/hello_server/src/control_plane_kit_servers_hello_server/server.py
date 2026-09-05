"""Tiny stdlib HTTP server used as an ordinary external product."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import socket
import sys
from threading import Lock
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


_DEPENDENCY_NAME = re.compile(r"[a-z][a-z0-9-]*\Z")
_MAX_RESPONSE_BYTES = 16_384
_OBSERVED_REQUEST_LIMIT = 20
_OBSERVED_REQUESTS: deque[dict[str, str]] = deque(maxlen=_OBSERVED_REQUEST_LIMIT)
_OBSERVED_REQUESTS_LOCK = Lock()
_ACCENTS = {
    "blue": ("#2563eb", "#eff6ff"),
    "purple": ("#7e22ce", "#faf5ff"),
    "green": ("#15803d", "#f0fdf4"),
    "red": ("#b91c1c", "#fef2f2"),
}


class HelloConfigurationError(ValueError):
    """Raised when runtime-supplied Hello configuration is malformed."""


def render_hello(message: str, color: str = "blue") -> bytes:
    """Return the deterministic root response for this Hello image contract."""

    if color not in _ACCENTS:
        raise HelloConfigurationError("HELLO_COLOR must be blue, purple, green or red")
    accent, fill = _ACCENTS[color]
    greeting = escape(message)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{greeting}</title>
<style>
* {{ box-sizing: border-box; }}
html {{ background: #fff; color: #171717; }}
body {{ margin: 0; min-height: 100svh; display: grid; place-items: center;
  padding: 24px; font-family: system-ui, sans-serif; letter-spacing: 0; }}
main {{ width: 100%; max-width: 880px; border: 2px solid {accent};
  padding: 24px; background: {fill}; }}
.frame {{ border: 2px solid {accent}; padding: 24px; }}
.greeting {{ min-height: 300px; display: grid; place-items: center;
  background: #fff; text-align: center; }}
h1 {{ margin: 0; max-width: 100%; font-size: 48px; line-height: 1.2;
  font-weight: 650; overflow-wrap: anywhere; }}
@media (max-width: 600px) {{
  body, main, .frame {{ padding: 12px; }}
  .greeting {{ min-height: 240px; }}
  h1 {{ font-size: 32px; }}
}}
</style>
</head>
<body>
<main><div class="frame"><div class="frame greeting"><h1>{greeting}</h1></div></div></main>
</body>
</html>
""".encode("utf-8")


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    """One named pair of HTTP and Postgres dependency environment bindings."""

    name: str
    http_environment: str
    database_environment: str

    def __post_init__(self) -> None:
        _validate_dependency_name(self.name)
        _validate_environment_name(self.http_environment)
        _validate_environment_name(self.database_environment)

    def check(self, environ: Mapping[str, str]) -> list[str]:
        failures: list[str] = []
        http_url = environ.get(self.http_environment)
        database_url = environ.get(self.database_environment)
        if http_url is None:
            failures.append(f"{self.name}: missing {self.http_environment}")
        else:
            failures.extend(_check_http(self.name, http_url))
        if database_url is None:
            failures.append(f"{self.name}: missing {self.database_environment}")
        else:
            failures.extend(_check_postgres(self.name, database_url))
        return failures

    def descriptor(self) -> dict[str, str]:
        return {
            "name": self.name,
            "http_environment": self.http_environment,
            "database_environment": self.database_environment,
        }


def dependency_environment_names(name: str) -> tuple[str, str]:
    """Return the conventional HTTP/Postgres environment pair for a dependency."""

    _validate_dependency_name(name)
    suffix = name.upper().replace("-", "_")
    return (
        f"HELLO_HTTP_{suffix}_URL",
        f"HELLO_DATABASE_{suffix}_URL",
    )


def load_dependencies(raw: str | None) -> tuple[DependencyCheck, ...]:
    """Decode the bounded runtime dependency declaration language."""

    if raw in (None, ""):
        return ()
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HelloConfigurationError("HELLO_DEPENDENCIES_JSON is invalid JSON") from error
    if not isinstance(decoded, list):
        raise HelloConfigurationError("HELLO_DEPENDENCIES_JSON must be a list")
    dependencies: list[DependencyCheck] = []
    seen: set[str] = set()
    for item in decoded:
        if not isinstance(item, dict) or set(item) - {
            "name",
            "http_environment",
            "database_environment",
        }:
            raise HelloConfigurationError("dependency declaration is malformed")
        name = _required_text(item, "name")
        if name in seen:
            raise HelloConfigurationError("dependency names must be unique")
        seen.add(name)
        http_environment = item.get("http_environment")
        database_environment = item.get("database_environment")
        if http_environment is None or database_environment is None:
            http_environment, database_environment = dependency_environment_names(name)
        dependencies.append(
            DependencyCheck(
                name=name,
                http_environment=_text(http_environment, "http_environment"),
                database_environment=_text(database_environment, "database_environment"),
            )
        )
    return tuple(dependencies)


class HelloHandler(BaseHTTPRequestHandler):
    server_version = "control-plane-kit-hello/1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health/live":
            self._send(200, b"live\n")
            return
        if self.path == "/health/ready":
            failures = _dependency_failures(os.environ)
            if failures:
                self._send(503, ("\n".join(failures) + "\n").encode("utf-8"))
            else:
                self._send(200, b"ready\n")
            return
        if self.path == "/dependencies":
            payload = json.dumps(
                [dependency.descriptor() for dependency in _dependencies()],
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self._send(200, payload, content_type="application/json")
            return
        if self.path == "/observations/requests":
            self._send(
                200,
                json.dumps(
                    _observed_requests_payload(),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
                content_type="application/json",
            )
            return
        if self.path == "/":
            _record_observed_request("GET", self.path)
            message = os.environ.get("HELLO_MESSAGE", "Hello, world!")
            self._send(
                200,
                render_hello(message, os.environ.get("HELLO_COLOR", "blue")),
                content_type="text/html; charset=utf-8",
            )
            return
        self._send(404, b"not found\n")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    port = _port(os.environ.get("HELLO_PORT", "8000"))
    render_hello(
        os.environ.get("HELLO_MESSAGE", "Hello, world!"),
        os.environ.get("HELLO_COLOR", "blue"),
    )
    server = ThreadingHTTPServer(("0.0.0.0", port), HelloHandler)
    server.serve_forever()
    return 0


def _dependency_failures(environ: Mapping[str, str]) -> list[str]:
    failures: list[str] = []
    for dependency in _dependencies():
        failures.extend(dependency.check(environ))
    return failures


def _dependencies() -> tuple[DependencyCheck, ...]:
    return load_dependencies(os.environ.get("HELLO_DEPENDENCIES_JSON", "[]"))


def _record_observed_request(method: str, target: str) -> None:
    parsed = urlsplit(target)
    observed = {"method": method, "path": parsed.path or "/"}
    with _OBSERVED_REQUESTS_LOCK:
        _OBSERVED_REQUESTS.append(observed)


def _observed_requests_payload() -> dict[str, object]:
    with _OBSERVED_REQUESTS_LOCK:
        requests = tuple(_OBSERVED_REQUESTS)
    return {
        "count": len(requests),
        "retained_limit": _OBSERVED_REQUEST_LIMIT,
        "requests": requests,
    }


def _clear_observed_requests() -> None:
    with _OBSERVED_REQUESTS_LOCK:
        _OBSERVED_REQUESTS.clear()


def _check_http(name: str, url: str) -> list[str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return [f"{name}: HTTP dependency URL is malformed"]
    request = Request(url, method="GET")
    opener = build_opener(NoRedirects)
    try:
        with opener.open(request, timeout=2) as response:
            response.read(_MAX_RESPONSE_BYTES + 1)
            if response.status >= 400:
                return [f"{name}: HTTP dependency returned {response.status}"]
    except HTTPError as error:
        return [f"{name}: HTTP dependency returned {error.code}"]
    except (OSError, URLError) as error:
        return [f"{name}: HTTP dependency unavailable: {type(error).__name__}"]
    return []


def _check_postgres(name: str, url: str) -> list[str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        return [f"{name}: Postgres dependency URL has unsupported scheme"]
    if not parsed.hostname:
        return [f"{name}: Postgres dependency URL is missing host"]
    port = parsed.port or 5432
    try:
        with socket.create_connection((parsed.hostname, port), timeout=2):
            return []
    except OSError as error:
        return [f"{name}: Postgres dependency unavailable: {type(error).__name__}"]


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise HelloConfigurationError("HELLO_PORT must be an integer") from error
    if not 1 <= port <= 65_535:
        raise HelloConfigurationError("HELLO_PORT must be between 1 and 65535")
    return port


def _required_text(value: Mapping[str, object], key: str) -> str:
    return _text(value.get(key), key)


def _text(value: object, key: str) -> str:
    if not isinstance(value, str) or value == "":
        raise HelloConfigurationError(f"{key} must be a nonempty string")
    return value


def _validate_dependency_name(value: str) -> None:
    if not isinstance(value, str) or _DEPENDENCY_NAME.fullmatch(value) is None:
        raise HelloConfigurationError(
            "dependency name must start with a lowercase letter and contain only "
            "lowercase letters, digits, and hyphens"
        )


def _validate_environment_name(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", value):
        raise HelloConfigurationError("dependency environment name is malformed")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HelloConfigurationError as error:
        print(f"hello-server configuration error: {error}", file=sys.stderr)
        raise SystemExit(2)
