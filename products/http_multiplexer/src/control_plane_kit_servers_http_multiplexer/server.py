"""Small stdlib HTTP multiplexer process."""

from __future__ import annotations

import http.server
import sys
import time
from http.server import ThreadingHTTPServer
from typing import Callable, Mapping
from urllib import error, request

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
    MultiplexerConfigurationError, MultiplexerSettings, MultiplexerControlConfiguration,
    read_multiplexer_control_configuration, multiplexer_control_configuration_artifact,
)


MAX_RESPONSE_BYTES = 1_048_576
MAX_OBSERVER_RESPONSE_BYTES = 16_384
DEFAULT_PORT = 8000


class NoRedirects(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise error.HTTPError(req.full_url, code, "redirects are disabled", headers, fp)


def forward_primary(
    settings: MultiplexerSettings,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
) -> tuple[int, bytes, str]:
    return _open(settings.primary_url + path, method, headers, body, MAX_RESPONSE_BYTES)


def deliver_observers(
    settings: MultiplexerSettings,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
) -> tuple[str, ...]:
    errors: list[str] = []
    for index, observer_url in enumerate(settings.observer_urls, start=1):
        try:
            _open(observer_url + path, method, headers, body, MAX_OBSERVER_RESPONSE_BYTES)
        except Exception:  # noqa: BLE001 - observers are explicitly fail-open.
            errors.append(f"observer-{index}: upstream-failure")
    return tuple(errors)


def _open(
    url: str,
    method: str,
    headers: Mapping[str, str],
    body: bytes,
    max_response_bytes: int,
) -> tuple[int, bytes, str]:
    opener = request.build_opener(NoRedirects)
    outbound = request.Request(url, data=body or None, method=method)
    for name, value in headers.items():
        lower = name.lower()
        if lower not in {"host", "connection", "content-length"}:
            outbound.add_header(name, value)
    with opener.open(outbound, timeout=5.0) as response:
        payload = response.read(max_response_bytes + 1)
        if len(payload) > max_response_bytes:
            raise RuntimeError("upstream response too large")
        content_type = response.headers.get("content-type", "application/octet-stream")
        return int(response.status), payload, content_type


def handler(settings: MultiplexerSettings) -> type[http.server.BaseHTTPRequestHandler]:
    class MultiplexerHandler(http.server.BaseHTTPRequestHandler):
        server_version = "control-plane-kit-http-multiplexer/1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health/live":
                self._send(200, b"live\n", "text/plain")
                return
            self._multiplex()

        def do_POST(self) -> None:  # noqa: N802
            self._multiplex()

        def do_PUT(self) -> None:  # noqa: N802
            self._multiplex()

        def do_PATCH(self) -> None:  # noqa: N802
            self._multiplex()

        def do_DELETE(self) -> None:  # noqa: N802
            self._multiplex()

        def log_message(self, format: str, *args: object) -> None:
            return

        def _multiplex(self) -> None:
            length = int(self.headers.get("content-length", "0") or "0")
            body = self.rfile.read(length) if length else b""
            try:
                status, payload, content_type = forward_primary(
                    settings,
                    self.command,
                    self.path,
                    self.headers,
                    body,
                )
            except Exception:
                self._send(502, b"primary request failed\n", "text/plain")
                return
            deliver_observers(settings, self.command, self.path, self.headers, body)
            self._send(status, payload, content_type)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return MultiplexerHandler


def install_multiplexer_control(server: ThreadingHTTPServer, config: MultiplexerControlConfiguration,
                                *, clock: Callable[[], int] = lambda: int(time.time())) -> None:
    audience = core.workload_node_control_audience(config.target)
    static = Ed25519WorkloadNodeControlSurfaceReadVerifier(
        AtomicWorkloadNodeControlSurfaceReadVerifierKeySet(config.surface_keys),
        expected_issuer=config.surface_issuer, expected_audience=audience, clock=clock,
    )
    health = Ed25519WorkloadNodeHealthReadVerifier(
        AtomicWorkloadNodeHealthReadVerifierKeySet(config.health_keys),
        expected_issuer=config.health_issuer, expected_audience=audience, clock=clock,
    )
    dispatcher = WorkloadNodeHealthReadDispatcher(
        target=config.target, runtime_id=config.runtime_id, declaration=config.declaration, verifier=health,
        liveness=lambda: core.NodeHealthReadOutcome.HEALTHY, readiness=None,
    )
    install_cpk_control_routes(
        server, reserve_control_namespace=True, target=config.target, declaration=config.declaration,
        variables=(), command_verifier=None, surface_read_verifier=static, health_dispatcher=dispatcher,
    )


def create_multiplexer_server(config: MultiplexerControlConfiguration, settings: MultiplexerSettings, *,
                             address: tuple[str, int] = ("0.0.0.0", 8000),
                             clock: Callable[[], int] = lambda: int(time.time())) -> ThreadingHTTPServer:
    """Install on an unbound standard host; the product owns its socket lifecycle."""
    multiplexer_control_configuration_artifact(config)
    if type(settings) is not MultiplexerSettings:
        raise MultiplexerConfigurationError("MULTIPLEXER_PRIMARY_URL, observer URL or PORT is invalid")
    server = ThreadingHTTPServer(address, handler(settings), bind_and_activate=False)
    try:
        install_multiplexer_control(server, config, clock=clock)
        server.server_bind()
        server.server_activate()
        return server
    except BaseException:
        server.server_close()
        raise


def main() -> int:
    try:
        settings = MultiplexerSettings.from_environment()
        if settings.port != DEFAULT_PORT:
            raise MultiplexerConfigurationError("wrapped multiplexer requires port 8000")
        config = read_multiplexer_control_configuration()
    except MultiplexerConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    server = create_multiplexer_server(config, settings, address=("0.0.0.0", DEFAULT_PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
