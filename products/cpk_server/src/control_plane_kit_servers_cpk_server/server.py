"""Runnable stdlib HTTP process for the cpk-server image."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping

from control_plane_kit_core.operations import ControlPlaneServiceRole

from .boundary import (
    CpkServerApplicationBoundary,
    CpkServerHttpProcessBoundary,
    CpkServerMcpProcessBoundary,
    CpkServerServiceRequest,
)
from .composition import (
    CpkServerCompositionError,
    CpkServerProcessConfiguration,
    create_cpk_server_composition,
)


class BootstrapConfigurationError(ValueError):
    """Raised when required process bootstrap configuration is missing."""


@dataclass(frozen=True, slots=True)
class CpkServerBootstrapConfiguration:
    mode: str
    control_auth_configured: bool
    port: int
    store_endpoints: Mapping[str, str]

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "CpkServerBootstrapConfiguration":
        values = dict(os.environ if environ is None else environ)
        mode = _required(values, "CPK_SERVER_MODE")
        auth = _required(values, "CPK_CONTROL_AUTH_CONFIGURED")
        port_text = _required(values, "CPK_PORT")
        store_endpoints = {
            name: _required(values, name)
            for name in (
                "CPK_WORKPLACE_DATABASE_URL",
                "CPK_ACTIVITY_HISTORY_DATABASE_URL",
                "CPK_OBSERVER_STATE_DATABASE_URL",
                "CPK_GRAPH_TOPOLOGY_DATABASE_URL",
            )
        }
        if mode != "execution-capable":
            raise BootstrapConfigurationError("CPK_SERVER_MODE must be execution-capable")
        if auth.lower() not in {"true", "1", "yes"}:
            raise BootstrapConfigurationError(
                "CPK_CONTROL_AUTH_CONFIGURED must be true for hosted cpk-server"
            )
        try:
            port = int(port_text)
        except ValueError as error:
            raise BootstrapConfigurationError("CPK_PORT must be an integer") from error
        if not 1 <= port <= 65535:
            raise BootstrapConfigurationError("CPK_PORT must be in TCP port range")
        return cls(
            mode=mode,
            control_auth_configured=True,
            port=port,
            store_endpoints=store_endpoints,
        )

    def process_configuration(self) -> CpkServerProcessConfiguration:
        return CpkServerProcessConfiguration.execution_capable(token_configured=True)


class _DemoService:
    def __init__(self, role: ControlPlaneServiceRole) -> None:
        self.role = role

    def handle(self, request: CpkServerServiceRequest) -> Mapping[str, object]:
        return {
            "service": self.role.value,
            "route_id": request.route_id,
            "surface": request.surface,
            "path_parameters": request.path_parameters,
            "payload": dict(request.payload),
        }


class _Handler(BaseHTTPRequestHandler):
    server_version = "cpk-server/0.1"

    def do_GET(self) -> None:
        if self.path == "/health/live":
            self._json(200, {"status": "live"})
            return
        if self.path == "/health/ready":
            self._json(
                200,
                {
                    "status": "ready",
                    "application": "configured",
                    "stores": "configured",
                },
            )
            return
        response = self.server.http_boundary.handle(
            method="GET",
            path=self.path,
            headers=_headers(self.headers),
            body=b"",
        )
        self._json(response.status, response.body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/mcp":
            try:
                message = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(400, {"error": {"status": 400, "message": "invalid JSON request body"}})
                return
            response = self.server.mcp_boundary.handle(
                headers=_headers(self.headers),
                message=message,
            )
        else:
            response = self.server.http_boundary.handle(
                method="POST",
                path=self.path,
                headers=_headers(self.headers),
                body=body,
            )
        self._json(response.status, response.body)

    def log_message(self, format: str, *args: object) -> None:
        safe = format.replace("Authorization", "[redacted]")
        super().log_message(safe, *args)

    def _json(self, status: int, payload: Mapping[str, object]) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def create_server(config: CpkServerBootstrapConfiguration) -> ThreadingHTTPServer:
    composition = create_cpk_server_composition(config.process_configuration())
    application = CpkServerApplicationBoundary(
        {role: _DemoService(role) for role in ControlPlaneServiceRole}
    )
    server = ThreadingHTTPServer(("0.0.0.0", config.port), _Handler)
    server.http_boundary = CpkServerHttpProcessBoundary(composition, application)
    server.mcp_boundary = CpkServerMcpProcessBoundary(composition, application)
    return server


def main() -> int:
    try:
        config = CpkServerBootstrapConfiguration.from_environment()
        server = create_server(config)
    except (BootstrapConfigurationError, CpkServerCompositionError) as error:
        print(f"cpk-server bootstrap error: {error}", flush=True)
        return 2
    print(f"cpk-server listening on 0.0.0.0:{config.port}", flush=True)
    server.serve_forever()
    return 0


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if value is None or value == "":
        raise BootstrapConfigurationError(f"{name} is required")
    return value


def _headers(headers) -> dict[str, str]:
    return {key: value for key, value in headers.items()}


if __name__ == "__main__":
    raise SystemExit(main())
