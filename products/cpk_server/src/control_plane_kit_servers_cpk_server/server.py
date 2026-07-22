"""Runnable FastAPI process for the cpk-server image."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Mapping
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import psycopg
import uvicorn
from control_plane_kit_core.operations.execution import EffectResultKind
from control_plane_kit_core.operations.lifecycle import FailureCategory
from control_plane_kit_operations import (
    ActivityExecutionOutcome,
    ActivityPlanningCommandService,
    ApprovalCommandService,
    BoundedEvidence,
    CpkServerOperationsApplication,
    ExecutionAdmissionCommandService,
    ExecutionCoordinator,
    FailureEvidence,
    RunLifecycleCommandService,
    cpk_server_services,
)
from control_plane_kit_operations.postgres import PostgresUnitOfWork, install_schema

from .boundary import (
    CpkServerApplicationBoundary,
    CpkServerHttpProcessBoundary,
    CpkServerMcpProcessBoundary,
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

    def operations_database_url(self) -> str:
        urls = set(self.store_endpoints.values())
        if len(urls) != 1:
            raise BootstrapConfigurationError(
                "current operations package requires all CPK_*_DATABASE_URL values "
                "to point at one instance database"
            )
        return next(iter(urls))


def create_app(config: CpkServerBootstrapConfiguration) -> FastAPI:
    """Create the hosted cpk-server FastAPI application."""

    composition = create_cpk_server_composition(config.process_configuration())
    application = CpkServerApplicationBoundary(_operations_application(config).services)
    http_boundary = CpkServerHttpProcessBoundary(composition, application)
    mcp_boundary = CpkServerMcpProcessBoundary(composition, application)
    app = FastAPI(
        title="cpk-server",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.http_boundary = http_boundary
    app.state.mcp_boundary = mcp_boundary

    @app.get("/health/live")
    async def live() -> JSONResponse:
        return _json_response(200, {"status": "live"})

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        return _json_response(
            200,
            {
                "status": "ready",
                "application": "configured",
                "stores": "configured",
            },
        )

    @app.post("/mcp")
    async def mcp(request: Request) -> JSONResponse:
        body = await request.body()
        try:
            message = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json_response(
                400,
                {"error": {"status": 400, "message": "invalid JSON request body"}},
            )
        response = mcp_boundary.handle(
            headers=dict(request.headers),
            message=message,
        )
        return _json_response(response.status, response.body)

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def http(path: str, request: Request) -> JSONResponse:
        response = http_boundary.handle(
            method=request.method,
            path=request.url.path,
            headers=dict(request.headers),
            body=await request.body(),
        )
        return _json_response(response.status, response.body)

    return app


def main() -> int:
    try:
        config = CpkServerBootstrapConfiguration.from_environment()
    except (BootstrapConfigurationError, CpkServerCompositionError) as error:
        print(f"cpk-server bootstrap error: {error}", flush=True)
        return 2
    print(f"cpk-server listening on 0.0.0.0:{config.port}", flush=True)
    uvicorn.run(
        create_app(config),
        host="0.0.0.0",
        port=config.port,
        access_log=False,
    )
    return 0


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if value is None or value == "":
        raise BootstrapConfigurationError(f"{name} is required")
    return value


def _operations_application(
    config: CpkServerBootstrapConfiguration,
) -> CpkServerOperationsApplication:
    database_url = config.operations_database_url()
    _install_operations_schema(database_url)

    def unit_of_work() -> PostgresUnitOfWork:
        return PostgresUnitOfWork(lambda: psycopg.connect(database_url))

    lifecycle = RunLifecycleCommandService(
        unit_of_work,
        clock=_clock,
        id_factory=_id,
    )
    execution = ExecutionCoordinator(
        unit_of_work,
        lifecycle=lifecycle,
        adapter=_UnsupportedExecutionAdapter(),
        clock=_clock,
        id_factory=_id,
    )
    return CpkServerOperationsApplication(
        cpk_server_services(
            unit_of_work_factory=unit_of_work,
            planning=ActivityPlanningCommandService(
                unit_of_work,
                clock=_clock,
                id_factory=_id,
            ),
            approval=ApprovalCommandService(
                unit_of_work,
                clock=_clock,
                id_factory=_id,
            ),
            admission=ExecutionAdmissionCommandService(
                unit_of_work,
                clock=_clock,
                id_factory=_id,
            ),
            lifecycle=lifecycle,
            execution=execution,
            clock=lambda: datetime.now(timezone.utc),
        )
    )


class _UnsupportedExecutionAdapter:
    """cpk-server wrapper default: operations exists, runtime effects do not."""

    def execute(self, activity) -> ActivityExecutionOutcome:
        return ActivityExecutionOutcome(
            EffectResultKind.UNSUPPORTED,
            failure=FailureEvidence(
                FailureCategory.UNSUPPORTED,
                "runtime-adapter-unavailable",
                "cpk-server image does not bundle a runtime effect interpreter",
                BoundedEvidence.from_mapping(
                    {"activity_id": activity.activity_id.value}
                ),
            ),
        )


def _install_operations_schema(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        install_schema(connection)
        connection.commit()


def _clock() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _id() -> str:
    return str(uuid4())


def _json_response(status: int, payload: Mapping[str, object]) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=dict(payload),
    )


if __name__ == "__main__":
    raise SystemExit(main())
