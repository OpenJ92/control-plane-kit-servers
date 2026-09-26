"""Tiny stdlib HTTP server used as an ordinary external product."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sys
import time
from threading import Lock
from typing import Callable, Mapping
from urllib.parse import urlsplit
import control_plane_kit_core as core
from control_plane_kit_server_sdk.health import WorkloadNodeHealthReadDispatcher
from control_plane_kit_server_sdk.stdlib import install_cpk_control_routes
from control_plane_kit_server_sdk.verification import (
    Ed25519WorkloadNodeControlSurfaceReadVerifier, Ed25519WorkloadNodeHealthReadVerifier,
)
from control_plane_kit_server_sdk.verifier_keys import (
    AtomicWorkloadNodeControlSurfaceReadVerifierKeySet, AtomicWorkloadNodeHealthReadVerifierKeySet,
)
from .configuration import (
    HelloConfigurationError, HelloControlConfiguration, hello_control_configuration_artifact,
    read_hello_control_configuration,
)
from .dependencies import DependencySnapshot, load_dependencies

_OBSERVED_REQUEST_LIMIT = 20
_ACCENTS = {
    "blue": ("#2563eb", "#eff6ff"),
    "purple": ("#7e22ce", "#faf5ff"),
    "green": ("#15803d", "#f0fdf4"),
    "red": ("#b91c1c", "#fef2f2"),
}


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


class HelloHandler(BaseHTTPRequestHandler):
    server_version = "control-plane-kit-hello/1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health/live":
            self._send(200, b"live\n")
            return
        if self.path == "/health/ready":
            try:
                status, body = self.server.hello_settings.inspect().legacy_response()
            except Exception:
                status, body = 500, b"dependency observation failed\n"
            self._send(status, body)
            return
        if self.path == "/dependencies":
            payload = json.dumps(
                [dependency.descriptor() for dependency in self.server.hello_settings.dependencies.dependencies],
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self._send(200, payload, content_type="application/json")
            return
        if self.path == "/observations/requests":
            self._send(
                200,
                json.dumps(
                    self.server.hello_observations.payload(),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
                content_type="application/json",
            )
            return
        if self.path == "/":
            self.server.hello_observations.record("GET", self.path)
            self._send(
                200,
                self.server.hello_settings.html,
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
    if port != 8000:
        raise HelloConfigurationError("wrapped Hello requires port 8000")
    render_hello(
        os.environ.get("HELLO_MESSAGE", "Hello, world!"),
        os.environ.get("HELLO_COLOR", "blue"),
    )
    config = read_hello_control_configuration()
    server = create_hello_server(config, os.environ, address=("0.0.0.0", port))
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


@dataclass(frozen=True, slots=True, repr=False)
class HelloSettings:
    html: bytes
    dependencies: DependencySnapshot
    clock: Callable[[], float]

    def inspect(self):
        return self.dependencies.inspect(clock=self.clock)


class RequestObservations:
    def __init__(self):
        self._requests = deque(maxlen=_OBSERVED_REQUEST_LIMIT)
        self._lock = Lock()

    def record(self, method: str, target: str) -> None:
        observed = {"method": method, "path": urlsplit(target).path or "/"}
        with self._lock:
            self._requests.append(observed)

    def payload(self) -> dict[str, object]:
        with self._lock:
            requests = tuple(dict(item) for item in self._requests)
        return {"count": len(requests), "retained_limit": _OBSERVED_REQUEST_LIMIT, "requests": requests}


def install_hello_control(server: ThreadingHTTPServer, config: HelloControlConfiguration,
                          *, clock: Callable[[], int]) -> None:
    audience = core.workload_node_control_audience(config.target)
    static = Ed25519WorkloadNodeControlSurfaceReadVerifier(
        AtomicWorkloadNodeControlSurfaceReadVerifierKeySet(config.surface_keys),
        expected_issuer=config.surface_issuer, expected_audience=audience, clock=clock,
    )
    health = Ed25519WorkloadNodeHealthReadVerifier(
        AtomicWorkloadNodeHealthReadVerifierKeySet(config.health_keys),
        expected_issuer=config.health_issuer, expected_audience=audience, clock=clock,
    )
    settings = server.hello_settings
    dispatcher = WorkloadNodeHealthReadDispatcher(
        target=config.target, runtime_id=config.runtime_id, declaration=config.declaration, verifier=health,
        liveness=lambda: core.NodeHealthReadOutcome.HEALTHY,
        readiness=lambda: settings.inspect().outcome,
    )
    install_cpk_control_routes(
        server, reserve_control_namespace=True, target=config.target, declaration=config.declaration,
        variables=(), command_verifier=None, surface_read_verifier=static, health_dispatcher=dispatcher,
    )


def create_hello_server(config: HelloControlConfiguration, environ: Mapping[str, str], *,
                        address: tuple[str, int] = ("0.0.0.0", 8000),
                        clock: Callable[[], int] = lambda: int(time.time()),
                        observation_clock: Callable[[], float] = time.monotonic) -> ThreadingHTTPServer:
    """Product-owned composition; ephemeral addresses are for package test hosts."""
    html = render_hello(environ.get("HELLO_MESSAGE", "Hello, world!"), environ.get("HELLO_COLOR", "blue"))
    dependencies = DependencySnapshot(load_dependencies(environ.get("HELLO_DEPENDENCIES_JSON", "[]")), environ)
    hello_control_configuration_artifact(config)  # Bound/revalidate local material before socket creation.
    settings = HelloSettings(html, dependencies, observation_clock)
    server = ThreadingHTTPServer(address, HelloHandler, bind_and_activate=False)
    try:
        server.hello_settings = settings
        server.hello_observations = RequestObservations()
        install_hello_control(server, config, clock=clock)
        server.server_bind()
        server.server_activate()
        return server
    except BaseException:
        server.server_close()
        raise


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise HelloConfigurationError("HELLO_PORT must be an integer") from error
    if not 1 <= port <= 65_535:
        raise HelloConfigurationError("HELLO_PORT must be between 1 and 65535")
    return port


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HelloConfigurationError as error:
        print(f"hello-server configuration error: {error}", file=sys.stderr)
        raise SystemExit(2)
