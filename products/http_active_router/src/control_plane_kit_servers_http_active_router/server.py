"""Small stdlib HTTP active router process."""

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
    RouterConfigurationError, RouterSettings, RouterControlConfiguration,
    read_router_control_configuration, router_control_configuration_artifact,
)


MAX_RESPONSE_BYTES = 1_048_576
DEFAULT_PORT = 8000


class NoRedirects(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise error.HTTPError(req.full_url, code, "redirects are disabled", headers, fp)


def forward(settings: RouterSettings, method: str, path: str, headers: Mapping[str, str], body: bytes) -> tuple[int, bytes, str]:
    target = settings.active_target_url + path
    opener = request.build_opener(NoRedirects)
    outbound = request.Request(target, data=body or None, method=method)
    for name, value in headers.items():
        lower = name.lower()
        if lower not in {"host", "connection", "content-length"}:
            outbound.add_header(name, value)
    try:
        with opener.open(outbound, timeout=5.0) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                return 502, b"upstream response too large\n", "text/plain"
            content_type = response.headers.get("content-type", "application/octet-stream")
            return int(response.status), payload, content_type
    except error.HTTPError as exc:
        payload = exc.read(MAX_RESPONSE_BYTES)
        return int(exc.code), payload, exc.headers.get("content-type", "text/plain")
    except Exception:  # pragma: no cover - exercised by Docker smoke.
        return 502, b"upstream request failed\n", "text/plain"


def handler(settings: RouterSettings) -> type[http.server.BaseHTTPRequestHandler]:
    class ActiveRouterHandler(http.server.BaseHTTPRequestHandler):
        server_version = "control-plane-kit-http-active-router/1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health/live":
                self._send(200, b"live\n", "text/plain")
                return
            self._forward()

        def do_POST(self) -> None:  # noqa: N802
            self._forward()

        def do_PUT(self) -> None:  # noqa: N802
            self._forward()

        def do_PATCH(self) -> None:  # noqa: N802
            self._forward()

        def do_DELETE(self) -> None:  # noqa: N802
            self._forward()

        def log_message(self, format: str, *args: object) -> None:
            return

        def _forward(self) -> None:
            length = int(self.headers.get("content-length", "0") or "0")
            body = self.rfile.read(length) if length else b""
            status, payload, content_type = forward(settings, self.command, self.path, self.headers, body)
            self._send(status, payload, content_type)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ActiveRouterHandler


def install_router_control(server: ThreadingHTTPServer, config: RouterControlConfiguration,
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


def create_router_server(config: RouterControlConfiguration, settings: RouterSettings, *,
                         address: tuple[str, int] = ("0.0.0.0", 8000),
                         clock: Callable[[], int] = lambda: int(time.time())) -> ThreadingHTTPServer:
    """Install on an unbound standard host; the product owns its socket lifecycle."""
    router_control_configuration_artifact(config)
    if type(settings) is not RouterSettings:
        raise RouterConfigurationError("ACTIVE_TARGET_URL or PORT is invalid")
    server = ThreadingHTTPServer(address, handler(settings), bind_and_activate=False)
    try:
        install_router_control(server, config, clock=clock)
        server.server_bind()
        server.server_activate()
        return server
    except BaseException:
        server.server_close()
        raise


def main() -> int:
    try:
        settings = RouterSettings.from_environment()
        if settings.port != DEFAULT_PORT:
            raise RouterConfigurationError("wrapped router requires port 8000")
        config = read_router_control_configuration()
    except RouterConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    server = create_router_server(config, settings, address=("0.0.0.0", DEFAULT_PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
