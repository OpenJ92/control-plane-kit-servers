"""HTTP-shaped and MCP-shaped process boundaries for cpk-server."""

from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass, field
import json
import math
import re
from typing import Any, Mapping, Protocol

from control_plane_kit_core.identity import (
    AuthenticatedPrincipal,
    CredentialVerifier,
)
from control_plane_kit_core.operations import (
    ControlPlaneServiceRole, HTTP_ONLY_COMMAND_ROUTE_IDS, InvalidEffectRecoveryContract,
)
from control_plane_kit_core.operations.http import (
    HttpApiRouteContract,
    HttpMethod,
    HttpOperationSafety,
)
from control_plane_kit_operations import (
    CpkServerApplicationError,
    CpkServerOperationsApplication,
    InvalidOperationCommand,
)

from .composition import CpkServerComposition, CpkServerCompositionError
from .request_body import MCP_ENVELOPE_MAX_BYTES, RequestBodyTooLarge, collect_request_body
from .authentication import (
    CredentialAuthenticationError,
    authenticate_bearer_credential,
)


class CpkServerService(Protocol):
    def handle(self, request: "CpkServerServiceRequest") -> Mapping[str, object]:
        ...


@dataclass(frozen=True, slots=True)
class CpkServerServiceRequest:
    """One bounded request delegated to an application service."""

    surface: str
    route_id: str
    service_role: ControlPlaneServiceRole
    path_parameters: dict[str, str]
    payload: Mapping[str, object] = field(repr=False)
    principal: AuthenticatedPrincipal


@dataclass(frozen=True, slots=True)
class CpkServerBoundaryResponse:
    """Small framework-neutral response value."""

    status: int
    body: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _HttpAdmission:
    route: HttpApiRouteContract
    path_parameters: tuple[tuple[str, str], ...]
    principal: AuthenticatedPrincipal


class CpkServerApplicationBoundary:
    """Shared service boundary used by HTTP and MCP process surfaces."""

    def __init__(
        self,
        services: CpkServerOperationsApplication | Mapping[ControlPlaneServiceRole, CpkServerService],
        credential_verifier: CredentialVerifier,
    ) -> None:
        configured = services if isinstance(services, CpkServerOperationsApplication) else None
        service_map = configured.services if configured is not None else services
        missing = tuple(role for role in ControlPlaneServiceRole if role not in service_map)
        if missing:
            missing_names = ", ".join(role.value for role in missing)
            raise CpkServerCompositionError(f"missing services: {missing_names}")
        if not callable(getattr(credential_verifier, "authenticate", None)):
            raise CpkServerCompositionError("credential verifier is required")
        # Mapping compatibility is explicitly static. An already configured
        # application retains its resolver, authority mode and service identity.
        self._application = (configured if configured is not None
            else CpkServerOperationsApplication(dict(service_map), authority_mode="static"))
        self._credential_verifier = credential_verifier

    def authenticate(
        self,
        headers: Mapping[str, str],
    ) -> AuthenticatedPrincipal:
        return authenticate_bearer_credential(headers, self._credential_verifier)

    def dispatch(self, request: CpkServerServiceRequest) -> Mapping[str, object]:
        return self._application.handle(request)

    async def dispatch_async(self, request: CpkServerServiceRequest) -> Mapping[str, object]:
        return await self._application.handle_async(request)


class CpkServerHttpProcessBoundary:
    """Framework-neutral HTTP process boundary over core route contracts."""

    def __init__(
        self,
        composition: CpkServerComposition,
        application: CpkServerApplicationBoundary,
    ) -> None:
        self.composition = composition
        self.application = application

    def handle(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
        query_string: bytes = b"",
    ) -> CpkServerBoundaryResponse:
        request = self._prepare(method, path, headers, body, query_string)
        if isinstance(request, CpkServerBoundaryResponse):
            return request
        return _http_response(_dispatch_application(self.application, request),
            self.composition.http_api.route(request.route_id))

    async def handle_async(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
        query_string: bytes = b"",
    ) -> CpkServerBoundaryResponse:
        request = self._prepare(method, path, headers, body, query_string)
        if isinstance(request, CpkServerBoundaryResponse):
            return request
        return _http_response(await _dispatch_application_async(self.application, request),
            self.composition.http_api.route(request.route_id))

    def _prepare(
        self, method: str, path: str, headers: Mapping[str, str],
        body: bytes, query_string: bytes,
    ) -> CpkServerServiceRequest | CpkServerBoundaryResponse:
        admission = self._admit(method, path, headers)
        if isinstance(admission, CpkServerBoundaryResponse):
            return admission
        return self._prepare_admitted(admission, body, query_string)

    async def handle_stream_async(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: AsyncIterable[bytes],
        query_string: bytes = b"",
    ) -> CpkServerBoundaryResponse:
        """Admit once before reading; retain only the matched route's budget."""
        admission = self._admit(method, path, headers)
        if isinstance(admission, CpkServerBoundaryResponse):
            return admission
        if admission.route.method is HttpMethod.GET:
            # Body refusal precedes query validation, as in the byte entrance.
            async for chunk in body:
                if chunk:
                    return _error(400, "read routes do not accept request bodies")
            collected = b""
        else:
            if query_string != b"":
                return _error(400, "command routes do not accept query arguments")
            try:
                collected = await collect_request_body(body, admission.route.request_schema.max_bytes)
            except RequestBodyTooLarge:
                return _error(413, "request body too large")
        request = self._prepare_admitted(admission, collected, query_string)
        if isinstance(request, CpkServerBoundaryResponse):
            return request
        return _http_response(await _dispatch_application_async(self.application, request),
            self.composition.http_api.route(request.route_id))

    def _admit(
        self, method: str, path: str, headers: Mapping[str, str],
    ) -> _HttpAdmission | CpkServerBoundaryResponse:
        route_match = _match_http_route(self.composition, method, path)
        if route_match is None:
            return _error(404, "unknown route")
        route, path_parameters = route_match
        try:
            principal = self.application.authenticate(headers)
        except CredentialAuthenticationError:
            return _error(401, "invalid credential")
        return _HttpAdmission(route, tuple(path_parameters.items()), principal)

    def _prepare_admitted(
        self, admission: _HttpAdmission, body: bytes, query_string: bytes,
    ) -> CpkServerServiceRequest | CpkServerBoundaryResponse:
        route = admission.route
        payload = _decode_http_payload(route, body, query_string)
        if isinstance(payload, CpkServerBoundaryResponse):
            return payload
        framing_error = _validate_reobserve_frame(route, payload, surface="http")
        if framing_error is not None:
            return framing_error
        return CpkServerServiceRequest(
            surface="http",
            route_id=route.route_id,
            service_role=route.service_role,
            path_parameters=dict(admission.path_parameters),
            payload=payload,
            principal=admission.principal,
        )


class CpkServerMcpProcessBoundary:
    """Framework-neutral MCP Streamable HTTP boundary over one application."""

    def __init__(
        self,
        composition: CpkServerComposition,
        application: CpkServerApplicationBoundary,
    ) -> None:
        self.composition = composition
        self.application = application

    def handle(
        self,
        *,
        headers: Mapping[str, str],
        message: Mapping[str, object],
    ) -> CpkServerBoundaryResponse:
        request = self._prepare(headers, message)
        if isinstance(request, CpkServerBoundaryResponse):
            return request
        return _mcp_response(message, _dispatch_application(self.application, request),
            self.composition.http_api.route(request.route_id))

    async def handle_async(
        self,
        *,
        headers: Mapping[str, str],
        message: Mapping[str, object],
    ) -> CpkServerBoundaryResponse:
        request = self._prepare(headers, message)
        if isinstance(request, CpkServerBoundaryResponse):
            return request
        return _mcp_response(message, await _dispatch_application_async(self.application, request),
            self.composition.http_api.route(request.route_id))

    async def handle_bytes_async(
        self, *, headers: Mapping[str, str], body: bytes,
    ) -> CpkServerBoundaryResponse:
        """Authenticate before strict raw JSON decoding, without losing duplicates."""
        if len(body) > MCP_ENVELOPE_MAX_BYTES:
            return _error(413, "request body too large")
        principal = self._admit(headers)
        if isinstance(principal, CpkServerBoundaryResponse):
            return principal
        try:
            message = _strict_json_object(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            return _error(400, "invalid JSON request body")
        request = self._prepare_admitted(headers, message, principal)
        if isinstance(request, CpkServerBoundaryResponse):
            return request
        return _mcp_response(message, await _dispatch_application_async(self.application, request),
            self.composition.http_api.route(request.route_id))

    def _prepare(
        self, headers: Mapping[str, str], message: Mapping[str, object],
    ) -> CpkServerServiceRequest | CpkServerBoundaryResponse:
        principal = self._admit(headers)
        if isinstance(principal, CpkServerBoundaryResponse):
            return principal
        return self._prepare_admitted(headers, message, principal)

    def _admit(self, headers: Mapping[str, str]) -> AuthenticatedPrincipal | CpkServerBoundaryResponse:
        header_error = _validate_mcp_headers(headers)
        if header_error is not None:
            return header_error
        try:
            principal = self.application.authenticate(headers)
        except CredentialAuthenticationError:
            return _error(401, "invalid credential")
        return principal

    def _prepare_admitted(
        self, headers: Mapping[str, str], message: Mapping[str, object],
        principal: AuthenticatedPrincipal,
    ) -> CpkServerServiceRequest | CpkServerBoundaryResponse:
        if not isinstance(message, Mapping):
            return _error(400, "MCP message must be an object")
        method_header = next(
            (value for key, value in headers.items() if key.lower() == "mcp-method"),
            None,
        )
        if method_header != message.get("method"):
            return _error(400, "MCP method header does not match message")
        return _decode_mcp_message(self.composition, message, principal)


def _http_response(
    response: Mapping[str, object] | CpkServerBoundaryResponse,
    route: HttpApiRouteContract,
) -> CpkServerBoundaryResponse:
    if isinstance(response, CpkServerBoundaryResponse):
        return response
    if route.service_role is ControlPlaneServiceRole.AUTHORIZATION:
        if _json_frame_error(response, route.response_schema.max_bytes) is not None:
            # A command may already have committed. This says nothing about
            # rollback, replay safety or the command's durable outcome.
            return _error(503, "application response unavailable")
    return CpkServerBoundaryResponse(200, dict(response))


def _mcp_response(
    message: Mapping[str, object],
    response: Mapping[str, object] | CpkServerBoundaryResponse,
    route: HttpApiRouteContract,
) -> CpkServerBoundaryResponse:
    if isinstance(response, CpkServerBoundaryResponse):
        return response
    normalized = _http_response(response, route)
    if normalized.status != 200:
        return normalized
    return CpkServerBoundaryResponse(
        200, {"jsonrpc": "2.0", "id": _message_id(message), "result": normalized.body},
    )


def _validate_reobserve_frame(
    route: HttpApiRouteContract, payload: Mapping[str, object], *, surface: str,
) -> CpkServerBoundaryResponse | None:
    if route.route_id != "command.deployment.reobserve-connector":
        return None
    # Wire framing only. Operations owns typed values, ranges and authority.
    fields = {"activity_id", "prior_attempt", "claim_generation", "idempotency_key"}
    if surface == "mcp":
        fields |= {"workspace_id", "run_id"}
        try:
            size = len(json.dumps(payload, ensure_ascii=True).encode("utf-8"))
        except (TypeError, ValueError, RecursionError):
            return _error(400, "invalid reobserve arguments")
        if size > route.request_schema.max_bytes:
            return _error(413, "request arguments too large")
    if set(payload) != fields:
        return _error(400, "invalid reobserve fields")
    return None


def _match_http_route(
    composition: CpkServerComposition,
    method: str,
    path: str,
) -> tuple[HttpApiRouteContract, dict[str, str]] | None:
    try:
        http_method = HttpMethod(method.upper())
    except ValueError:
        return None
    for route in composition.http_api.routes:
        if route.method is not http_method:
            continue
        parameters = _match_path_template(route.path_template, path)
        if parameters is not None:
            return route, parameters
    return None


def _match_path_template(template: str, path: str) -> dict[str, str] | None:
    names = re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", template)
    pattern = "^" + re.sub(r"\{[A-Za-z_][A-Za-z0-9_]*\}", r"([^/]+)", template) + "$"
    match = re.match(pattern, path)
    if match is None:
        return None
    return dict(zip(names, match.groups(), strict=True))


def _decode_http_payload(
    route: HttpApiRouteContract,
    body: bytes,
    query_string: bytes,
) -> Mapping[str, object] | CpkServerBoundaryResponse:
    if route.method is HttpMethod.GET:
        if body not in {b"", None}:
            return _error(400, "read routes do not accept request bodies")
        if len(query_string) > route.request_schema.max_bytes:
            return _error(413, "request query too large")
        return _decode_http_read_query(route, query_string)
    if query_string != b"":
        return _error(400, "command routes do not accept query arguments")
    if len(body) > route.request_schema.max_bytes:
        return _error(413, "request body too large")
    if body == b"":
        return {}
    try:
        decoded = (_strict_json_object(body.decode("utf-8"))
            if route.service_role is ControlPlaneServiceRole.AUTHORIZATION
            else json.loads(body.decode("utf-8")))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return _error(400, "invalid JSON request body")
    if not isinstance(decoded, dict):
        return _error(400, "request body must be an object")
    return decoded


def _decode_http_read_query(
    route: HttpApiRouteContract,
    query_string: bytes,
) -> Mapping[str, object] | CpkServerBoundaryResponse:
    if query_string == b"":
        return {}
    if not isinstance(query_string, bytes):
        return _error(400, "invalid query arguments")

    administration_fields = {
        "read.workspace-permissions": {"limit", "after"},
        "read.workspace-permission": {"target"},
        "read.workspace-permission-history": {"target", "limit", "after"},
        "read.managed-runtime-assignments": {"limit", "after"},
        "read.managed-runtime-assignment": {"runtime_id", "authority_ref"},
        "read.managed-runtime-assignment-history": {"runtime_id", "authority_ref", "limit", "after"},
        "read.provider-policy-command": set(),
        "read.provider-policy-grant": set(),
        "read.provider-policy-grants": {
            "subject", "workspace_id", "action", "intent_mode", "intent", "limit", "after_grant_id"},
    }
    fields = administration_fields.get(route.route_id, (
        {"expected", "pending_draft"}
        if route.route_id == "read.receiver-authoring-context"
        else {"limit", "after"}
    ))
    arguments: dict[str, object] = {}
    for field in query_string.split(b"&"):
        if field == b"" or b"=" not in field:
            return _error(400, "invalid query arguments")
        encoded_name, encoded_value = field.split(b"=", 1)
        try:
            name = _strict_percent_decode(encoded_name).decode("utf-8")
            value = _strict_percent_decode(encoded_value).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return _error(400, "invalid query arguments")
        if name not in fields or name in arguments:
            return _error(400, "invalid query arguments")
        if name in {"runtime_id", "authority_ref"} or (
                route.route_id == "read.provider-policy-grants" and name != "limit"):
            arguments[name] = value
            continue
        if name == "limit":
            if re.fullmatch(r"[1-9][0-9]*", value) is None:
                return _error(400, "invalid query arguments")
            try:
                arguments[name] = int(value)
            except ValueError:
                return _error(400, "invalid query arguments")
            continue
        try:
            decoded = json.loads(
                value,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
                parse_float=_parse_finite_json_float,
            )
        except (json.JSONDecodeError, RecursionError, ValueError):
            return _error(400, "invalid query arguments")
        if (name in {"after", "target"} and not isinstance(decoded, dict)) or _json_nesting(decoded) > 64:
            return _error(400, "invalid query arguments")
        arguments[name] = decoded
    return arguments


def _strict_percent_decode(value: bytes) -> bytes:
    decoded = bytearray()
    index = 0
    while index < len(value):
        byte = value[index]
        if byte != ord("%"):
            decoded.append(byte)
            index += 1
            continue
        if index + 2 >= len(value):
            raise ValueError("incomplete percent escape")
        digits = value[index + 1 : index + 3]
        if any(digit not in b"0123456789ABCDEFabcdef" for digit in digits):
            raise ValueError("invalid percent escape")
        decoded.append(int(digits, 16))
        index += 3
    return bytes(decoded)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _strict_json_object(value: str) -> dict[str, object]:
    decoded = json.loads(value, object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant, parse_float=_parse_finite_json_float)
    if not isinstance(decoded, dict) or _json_nesting(decoded) > 64:
        raise ValueError("invalid JSON object")
    return decoded


def _json_frame_error(value: Mapping[str, object], budget: int) -> int | None:
    """Bound encoded owner values; the JSON-RPC envelope is a separate frame."""
    if _json_nesting(value) > 64:
        return 400
    size = 0
    try:
        for chunk in json.JSONEncoder(ensure_ascii=True, allow_nan=False,
                separators=(",", ":")).iterencode(value):
            size += len(chunk.encode("utf-8"))
            if size > budget:
                return 413
    except (TypeError, ValueError, RecursionError):
        return 400
    return None


def _reject_json_constant(_value: str) -> object:
    raise ValueError("invalid JSON constant")


def _parse_finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite JSON number")
    return parsed


def _json_nesting(value: object) -> int:
    maximum = 0
    pending = [(value, 1)]
    while pending:
        current, depth = pending.pop()
        if not isinstance(current, (Mapping, list)):
            continue
        maximum = max(maximum, depth)
        if maximum > 64:
            return maximum
        children = current.values() if isinstance(current, Mapping) else current
        pending.extend((child, depth + 1) for child in children)
    return maximum


def _validate_mcp_headers(headers: Mapping[str, str]) -> CpkServerBoundaryResponse | None:
    lowered = {key.lower(): value for key, value in headers.items()}
    if "accept" not in lowered:
        return _error(400, "missing MCP Accept header")
    if "mcp-protocol-version" not in lowered:
        return _error(400, "missing MCP protocol version")
    if "mcp-method" not in lowered:
        return _error(400, "missing MCP method")
    return None


def _decode_mcp_message(
    composition: CpkServerComposition,
    message: Mapping[str, object],
    principal: AuthenticatedPrincipal,
) -> CpkServerServiceRequest | CpkServerBoundaryResponse:
    if not isinstance(message, Mapping):
        return _error(400, "MCP message must be an object")
    if message.get("jsonrpc") != "2.0":
        return _error(400, "MCP message must be JSON-RPC 2.0")
    method = message.get("method")
    params = message.get("params")
    if method not in {"tools/call", "resources/read"}:
        return _error(404, "unknown MCP method")
    if not isinstance(params, Mapping):
        return _error(400, "MCP params must be an object")
    name = params.get("name")
    if not isinstance(name, str):
        return _error(400, "MCP operation name must be text")
    route = _mcp_route(composition, method, name)
    if route is None or route.route_id in HTTP_ONLY_COMMAND_ROUTE_IDS:
        return _error(404, "unknown MCP operation")
    arguments = params.get("arguments", {})
    if not isinstance(arguments, Mapping):
        return _error(400, "MCP arguments must be an object")
    if method == "tools/call" and route.safety is HttpOperationSafety.READ_ONLY:
        return _error(400, "tools/call requires a command route")
    if method == "resources/read" and route.safety is not HttpOperationSafety.READ_ONLY:
        return _error(400, "resources/read requires a read route")
    if route.service_role is ControlPlaneServiceRole.AUTHORIZATION:
        framing_status = _json_frame_error(arguments, route.request_schema.max_bytes)
        if framing_status is not None:
            return _error(framing_status, "invalid request arguments"
                if framing_status == 400 else "request arguments too large")
    framing_error = _validate_reobserve_frame(route, arguments, surface="mcp")
    if framing_error is not None:
        return framing_error
    return CpkServerServiceRequest(
        surface="mcp",
        route_id=route.route_id,
        service_role=route.service_role,
        path_parameters={},
        payload=dict(arguments),
        principal=principal,
    )


def _mcp_route(
    composition: CpkServerComposition,
    method: object,
    name: str,
) -> HttpApiRouteContract | None:
    bindings = (
        composition.handoff.projection_parity.projections
        if method == "resources/read"
        else composition.handoff.command_parity.commands
    )
    for binding in bindings:
        if binding.mcp_tool_name == name:
            return composition.http_api.route(binding.http_route_id)
    try:
        return composition.http_api.route(name)
    except ValueError:
        return None


def _message_id(message: Mapping[str, object]) -> object:
    value = message.get("id")
    if isinstance(value, (str, int)):
        return value
    return None


def _error(status: int, message: str) -> CpkServerBoundaryResponse:
    return CpkServerBoundaryResponse(
        status,
        {
            "error": {
                "message": message,
                "status": status,
            }
        },
    )


def _dispatch_application(
    application: CpkServerApplicationBoundary,
    request: CpkServerServiceRequest,
) -> Mapping[str, object] | CpkServerBoundaryResponse:
    try:
        return application.dispatch(request)
    except Exception as error:  # noqa: BLE001 - bounded process response.
        return _application_error(error)


async def _dispatch_application_async(
    application: CpkServerApplicationBoundary,
    request: CpkServerServiceRequest,
) -> Mapping[str, object] | CpkServerBoundaryResponse:
    try:
        return await application.dispatch_async(request)
    except Exception as error:  # noqa: BLE001 - cancellation is not an Exception.
        return _application_error(error)


def _application_error(error: Exception) -> CpkServerBoundaryResponse:
    if isinstance(error, CpkServerApplicationError):
        return CpkServerBoundaryResponse(error.status, error.descriptor())
    if isinstance(error, (InvalidOperationCommand, InvalidEffectRecoveryContract)):
        return _error(400, "invalid operation arguments")
    return _error(500, "application service failed")
