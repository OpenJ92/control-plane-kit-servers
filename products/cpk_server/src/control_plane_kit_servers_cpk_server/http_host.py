"""Literal FastAPI hosting; operator semantics remain in the neutral boundary."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from control_plane_kit_core.operations import HttpApiContract
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response


_METHODS = ("GET", "POST")


def install_operator_http_routes(
    app: FastAPI,
    contract: HttpApiContract,
    endpoint: Callable[[Request], Awaitable[Response]],
) -> None:
    """Register after exact health/MCP handlers and before SDK installation.

    Validate every operator prefix before changing the host. These standard
    literal routes preserve the original request, including its empty/slashed
    tail, for the existing strict boundary matcher. They do not match SDK paths.
    """
    prefixes = set()
    for route in contract.routes:
        first = route.path_template.split("/", 2)[1]
        if (
            not first or "{" in first or "}" in first or first == "__control"
            or str(route.method) not in _METHODS
        ):
            raise ValueError("operator HTTP contract requires disjoint literal GET/POST prefixes")
        prefixes.add(first)

    # The exact public handlers were registered first. These fallthroughs also
    # retain their old method/slash errors without a wildcard at the root.
    for prefix in sorted(prefixes | {"health", "mcp"}):
        app.add_api_route(f"/{prefix}", endpoint, methods=list(_METHODS))
        app.add_api_route(f"/{prefix}/{{path:path}}", endpoint, methods=list(_METHODS))
    app.add_exception_handler(HTTPException, _application_http_exception)


async def _application_http_exception(request: Request, error: HTTPException) -> Response:
    # ASGI path is already decoded. Follow that single framework namespace;
    # extra URL decoding here would disagree with SDK route matching.
    if request.scope["path"].split("/", 2)[1] == "__control":
        return await http_exception_handler(request, error)
    if error.status_code in (404, 405):
        if request.method in _METHODS:
            return JSONResponse(
                {"error": {"status":404, "message":"unknown route"}}, status_code=404,
            )
        if error.status_code == 404:
            # An unmatched method formerly matched the root GET/POST route.
            error = HTTPException(405, headers={"Allow":", ".join(_METHODS)})
    # Genuine method mismatches retain the matched route's actual Allow header.
    return await http_exception_handler(request, error)
