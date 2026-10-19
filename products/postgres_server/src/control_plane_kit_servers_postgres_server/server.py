"""Protected SDK management host for the native PostgreSQL child."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import time
from typing import Callable

from control_plane_kit_core.receiver_configuration import ReceiverNodeControlConfiguration
from control_plane_kit_server_sdk.stdlib import CpkThreadingHTTPServer

from .configuration import postgres_control_configuration_artifact
from .readiness import ReadinessController


class ManagementHandler(BaseHTTPRequestHandler):
    server_version = "control-plane-kit-postgres/1"

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def create_management_server(
    configuration: ReceiverNodeControlConfiguration,
    readiness: ReadinessController,
    *,
    address: tuple[str, int] = ("0.0.0.0", 8000),
    clock: Callable[[], int] = lambda: int(time.time()),
) -> CpkThreadingHTTPServer:
    postgres_control_configuration_artifact(configuration)
    host = CpkThreadingHTTPServer(
        address,
        ManagementHandler,
        bind_and_activate=False,
        configuration=configuration,
        clock=clock,
        readiness=readiness.inspect,
    )
    try:
        host.daemon_threads = True
        host.server_bind()
        host.server_activate()
        return host
    except BaseException:
        host.server_close()
        raise
