"""Official MCP transport composed over the existing authenticated application."""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
import re

from control_plane_kit_core.operations import HTTP_ONLY_COMMAND_ROUTE_IDS
from jsonschema import Draft202012Validator
from mcp.server import Server
from mcp.types import CallToolResult, JSONRPCMessage, ListToolsResult, TextContent, Tool, ToolAnnotations
from pydantic import TypeAdapter, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from .authentication import CredentialAuthenticationError
from .boundary import (
    CpkServerBoundaryResponse, CpkServerServiceRequest, _dispatch_application_async,
    _json_frame_error, _strict_json_object, _validate_reobserve_frame,
)
from .request_body import MCP_ENVELOPE_MAX_BYTES, RequestBodyTooLarge, collect_request_body


_MESSAGE = TypeAdapter(JSONRPCMessage)


# Deliberately curated: route semantics and authorization remain with Operations.
# Names come from the existing Core parity contract, not another command vocabulary.
_READS = {
    "read.workspace": "Inspect workspace graph/revision coordinates and current state.",
    "read.current-graph": "Read the current graph as a redacted public observation, not an executable export.",
    "read.desired-graph": "Read Desired as a redacted public observation, not original authored source bytes.",
    "read.desired-topology-drafts": "List saved topology drafts.",
    "read.desired-topology-draft-revisions": "List revisions of one saved topology draft.",
    "read.desired-topology-draft-revision": "Read an exact saved revision identity and its redacted public graph projection.",
    "read.desired-topology-draft-revision-preparations": "Find recorded preparations for an exact saved revision, including after interruption.",
    "read.desired-topology-draft-revision-attempts": "Read deployment attempt history for an exact saved revision.",
    "read.sessions": "List open sessions; session identity is separate from a transport request ID.",
    "read.session-detail": "Inspect one durable session.",
    "read.session-plans": "List plans in a known durable session; do not infer an ambiguous operation from latest ordering.",
    "read.plan-detail": "Inspect an existing plan; reading it does not approve or execute it.",
    "read.approval-detail": "Inspect an existing approval request; reading never approves or executes the plan.",
    "read.plan-runs": "Read runs associated with a plan.",
    "read.run-events": "Read durable events for one run.",
    "read.workspace-permission": "Inspect an explicit principal's workspace permissions; this grants no authority.",
    "read.managed-runtime-assignment": "Inspect an explicit runtime management assignment; this grants no authority.",
    "read.runtime-authority-deliveries": "Inspect admitted runtime delivery metadata. Requires runtime-authority-delivery:read; denied access does not mean no delivery exists.",
}
_PAGED = {
    "read.desired-topology-drafts", "read.desired-topology-draft-revisions",
    "read.desired-topology-draft-revision-preparations", "read.desired-topology-draft-revision-attempts",
    "read.sessions", "read.session-plans", "read.plan-runs", "read.run-events", "read.runtime-authority-deliveries",
}
_EXTRA_FIELDS = {
    "read.workspace-permission": {"target": {"type": "object", "description": "Explicit principal identity: issuer, subject_id and kind."}},
    "read.managed-runtime-assignment": {"runtime_id": {"type": "string"}, "authority_ref": {"type": "string"}},
}


def _input_schema(route):
    if route.route_id == "command.deployment.prepare":
        lineage = {"type": "object", "properties": {
            "authored_graph_id": {"type": "string"}, "realized_projection_id": {"type": "string"}},
            "required": ["authored_graph_id", "realized_projection_id"], "additionalProperties": False}
        properties = {
            "workspace_id": {"type": "string"}, "draft_id": {"type": "string"},
            "revision": {"type": "integer", "minimum": 1},
            "expected_current": lineage, "expected_desired": lineage,
            "expected_desired_graph_revision": {"type": "integer", "minimum": 1},
            "title": {"type": "string"}, "idempotency_key": {"type": "string",
                "description": "Caller-owned durable key for this exact intent; not the JSON-RPC request ID."}}
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
    coordinates = re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", route.path_template)
    properties = {name: {"type": "integer" if name == "revision" else "string"}
                  for name in coordinates}
    extra = _EXTRA_FIELDS.get(route.route_id, {})
    properties.update(extra)
    required = coordinates + list(extra)
    if route.route_id in _PAGED:
        properties.update(limit={"type": "integer", "minimum": 1},
                          after={"type": "object", "description": "Unmodified cursor returned by this collection."})
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _result(body, *, error=False):
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(body, ensure_ascii=True, allow_nan=False))],
                          structured_content=dict(body), is_error=error)


def _failure(status, message):
    return _result({"error": {"status": status, "message": message}}, error=True)


class StandardMcpAdapter:
    """One SDK server; every HTTP request brings its own verified principal."""

    def __init__(self, composition, application):
        self.composition, self.application = composition, application
        self.routes, self.tools = {}, {}
        for binding in composition.handoff.projection_parity.projections:
            route = composition.http_api.route(binding.http_route_id)
            if route.route_id not in _READS or route.route_id in HTTP_ONLY_COMMAND_ROUTE_IDS:
                continue
            name = binding.mcp_tool_name
            self.routes[name] = route
            self.tools[name] = Tool(name=name, description=_READS[route.route_id],
                input_schema=_input_schema(route),
                output_schema={"type": "object", "description": "Bounded public " + route.response_schema.name + "; owner fields are preserved."},
                annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False,
                                            idempotent_hint=True, open_world_hint=False))
        binding = next(item for item in composition.handoff.command_parity.commands
                       if item.http_route_id == "command.deployment.prepare")
        route = composition.http_api.route(binding.http_route_id)
        self.routes[binding.mcp_tool_name] = route
        self.tools[binding.mcp_tool_name] = Tool(name=binding.mcp_tool_name,
            description="Request a plan for an already selected saved draft/revision. Requires instance:workspace:edit and plan:request; "
                "runtime delivery admission may also be required. Supply observed lineage/generation and retain the domain idempotency key. "
                "CPK owns its session. This does not select/resave a graph, approve or execute. This endpoint does not support "
                "a managed-verification/readiness-intent input here. After interruption query existing references; ambiguous association stays uncertain.",
            input_schema=_input_schema(route), output_schema={"type": "object", "description": "Bounded owner preparation result or safe error; preserves plan/approval references."},
            annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
        self.sdk = Server("cpk-server", version="0.1.0", on_list_tools=self.list_tools,
            on_call_tool=self.call_tool, get_tool_input_schema=lambda name: self.tools[name].input_schema if name in self.tools else None,
            instructions="Inspect workspace and exact saved revision first. Graph views are redacted observations, not source exports. "
                "CPK owns authorization, planning, approval and durable history. Transport IDs are not idempotency keys. "
                "After an interrupted command, query its existing durable references; never blindly replay a mutation.")
        self.sdk_app = None

    @asynccontextmanager
    async def lifespan(self):
        # SDK managers are single-use. Each host lifespan owns a matching fresh
        # transport/manager pair; CPK services and request authentication persist.
        sdk_app = self.sdk.streamable_http_app(json_response=True, stateless_http=True,
            max_request_body_size=MCP_ENVELOPE_MAX_BYTES)
        async with sdk_app.router.lifespan_context(sdk_app):
            self.sdk_app = sdk_app
            try:
                yield
            finally:
                self.sdk_app = None

    async def list_tools(self, ctx, params):
        return ListToolsResult(tools=list(self.tools.values()))

    async def call_tool(self, ctx, params):
        route = self.routes.get(params.name)
        if route is None or route.route_id in HTTP_ONLY_COMMAND_ROUTE_IDS:
            return _failure(404, "unknown MCP operation")
        arguments = params.arguments if params.arguments is not None else {}
        framing = _json_frame_error(arguments, route.request_schema.max_bytes)
        if framing is not None:
            return _failure(framing, "invalid request arguments" if framing == 400 else "request arguments too large")
        if not Draft202012Validator(self.tools[params.name].input_schema).is_valid(arguments):
            return _failure(400, "invalid request arguments")
        error = _validate_reobserve_frame(route, arguments, surface="mcp")
        if error is not None:
            return _result(error.body, error=True)
        # SDK supplies the current HTTP request, including on legacy requests.
        # No principal is captured from initialize or stored against a session ID.
        principal = ctx.request.state.cpk_mcp_principal
        response = await _dispatch_application_async(self.application, CpkServerServiceRequest(
            surface="mcp", route_id=route.route_id, service_role=route.service_role,
            path_parameters={}, payload=dict(arguments), principal=principal))
        if isinstance(response, CpkServerBoundaryResponse):
            if _json_frame_error(response.body, 8192) is not None:
                return _failure(503, "application response unavailable")
            return _result(response.body, error=True)
        if _json_frame_error(response, route.response_schema.max_bytes) is not None:
            # The owner might already have committed; no rollback/retry claim.
            return _failure(503, "application response unavailable")
        return _result(response)

    async def __call__(self, scope, receive, send):
        request = Request(scope, receive)
        body = None
        rejection = None
        if request.method == "POST":
            try:
                body = await collect_request_body(request.stream(), MCP_ENVELOPE_MAX_BYTES)
            except RequestBodyTooLarge:
                rejection = (413, "request body too large")
            if rejection is not None:
                await self._reject(scope, receive, send, *rejection)
                return
        try:
            principal = self.application.authenticate(request.headers)
        except CredentialAuthenticationError:
            rejection = (401, "invalid credential")
        if rejection is not None:
            await self._reject(scope, receive, send, *rejection)
            return
        if body is not None:
            try:
                decoded = _strict_json_object(body.decode("utf-8"))
                # The released SDK's legacy transport renders Pydantic envelope
                # diagnostics with input values. Admit using that SDK model but
                # reject privately here; the SDK still owns protocol semantics.
                _MESSAGE.validate_python(decoded, by_name=False)
            except (UnicodeDecodeError, ValueError, ValidationError, RecursionError):
                rejection = (400, "invalid JSON request body")
            if rejection is not None:
                # A send failure must not inherit confidential error context.
                await self._reject(scope, receive, send, *rejection)
                return
        scope = {**scope, "state": {**scope.get("state", {}), "cpk_mcp_principal": principal}}
        pending = body

        async def replay():
            nonlocal pending
            if pending is not None:
                data, pending = pending, None
                return {"type": "http.request", "body": data, "more_body": False}
            return await receive()

        sdk_app = self.sdk_app
        if sdk_app is None:
            await self._reject(scope, receive, send, 503, "MCP transport unavailable")
            return
        await sdk_app(scope, replay, send)

    @staticmethod
    async def _reject(scope, receive, send, status, message):
        await JSONResponse({"error": {"status": status, "message": message}}, status_code=status,
            headers={"WWW-Authenticate": "Bearer"} if status == 401 else None)(scope, receive, send)
