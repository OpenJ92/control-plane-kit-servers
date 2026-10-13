"""#251 fixture boundaries; CPK and Docker retain all execution semantics."""
from dataclasses import dataclass
import json

import httpx

from control_plane_kit_core.planning import StartNode, StartRuntime
from control_plane_kit_core.runtime_effects import EffectResultKind


class FixtureBoundaryFailure(RuntimeError):
    """Fatal test setup/observation failure; never a retryable HTTP failure."""


@dataclass(frozen=True)
class CompletedRuntimeCall:
    request: object
    result: object


class RecordedDockerRuntime:
    """Delegate once, retain the genuine request/result; no effect interpretation."""
    def __init__(self, runtime):
        self.runtime = runtime
        self.completed = []

    def execute(self, request):
        result = self.runtime.execute(request)
        self.completed.append(CompletedRuntimeCall(request, result))
        return result

    def execute_with_authority(self, request, authority):
        result = self.runtime.execute_with_authority(request, authority)
        self.completed.append(CompletedRuntimeCall(request, result))
        return result


def public_page(transport, route, workspace, **coordinates):
    """Bounded authenticated reads, preserving the owner's pagination contract."""
    items, after = [], None
    for _ in range(16):
        payload = {"limit": 100}
        if after is not None:
            payload["after"] = after
        page = transport.call(route,
            path_parameters={"workspace_id": workspace, **coordinates},
            payload=payload, credential_role="operator")
        items.extend(page["items"])
        after = page.get("next_cursor")
        if after is None:
            return items
    raise FixtureBoundaryFailure("public history exceeded fixture bound")


def require_committed_call(record, response, arguments, events):
    """The response activity is NEXT ready; correlate completed public events."""
    request, result = record.request, record.result
    path, body = arguments["path_parameters"], arguments["payload"]
    if (path["workspace_id"] != request.source.workspace_id
            or path["run_id"] != request.source.run_id.value
            or response.get("run_id") != path["run_id"]
            or body.get("max_effects") != 1
            or type(body.get("claim_generation")) is not int
            or body["claim_generation"] < 1
            or response.get("effects_attempted") != 1
            or (response.get("coordinator_status"), response.get("run_status"))
                not in {("progressed", "running"), ("completed", "succeeded")}
            or result.kind is not EffectResultKind.SUCCEEDED
            or result.effect_id != request.effect_id
            or request.effect_id != request.source.intent_event_id):
        raise FixtureBoundaryFailure("runtime/public result correlation failed")
    activity = request.activity_id.value
    starts = [value for value in events if value["event_id"] == request.effect_id]
    if (len(starts) != 1 or starts[0]["event_type"] != "step_started"
            or starts[0]["run_id"] != path["run_id"]
            or starts[0]["activity_id"] != activity):
        raise FixtureBoundaryFailure("original public start event is absent")
    later = [value for value in events if value["activity_id"] == activity
        and value["ordinal"] > starts[0]["ordinal"]]
    if (len(later) != 1 or later[0]["event_type"] != "step_succeeded"
            or later[0]["run_id"] != path["run_id"] or later[0].get("failure") is not None):
        raise FixtureBoundaryFailure("committed public success is ambiguous")


class AttachedPublicTransport:
    """Observe a genuine public response, attach the declared fixture, return it.

    A post-response hook fault is latched so the successful response reaches the
    normal client journal. The next mutation is refused before HTTP dispatch;
    the witness also calls require_healthy after apply returns.
    """
    def __init__(self, inner, runtime, placement):
        self.inner, self.runtime, self.placement = inner, runtime, placement
        self.failure = None
        self.unsent = []
        self.responses = []
        self.preparations = []

    def require_healthy(self):
        if self.failure is not None:
            raise FixtureBoundaryFailure("post-response fixture boundary failed") from None

    def call(self, route_id, **arguments):
        if self.failure is not None and route_id.startswith("command."):
            self.unsent.append(route_id)
            self.require_healthy()
        before = len(self.runtime.completed)
        response = self.inner.call(route_id, **arguments)
        if route_id == "command.deployment.prepare":
            self.preparations.append((arguments, response))
        if route_id != "command.deployment.execute":
            return response
        self.responses.append(response)
        completed = self.runtime.completed[before:]
        trigger = any(type(value.request.operation) in (StartRuntime, StartNode)
            for value in completed)
        if not trigger:
            return response
        try:
            if len(completed) != 1:
                raise FixtureBoundaryFailure("public call did not contain one runtime effect")
            record = completed[0]
            events = public_page(self.inner, "read.run-events",
                arguments["path_parameters"]["workspace_id"],
                run_id=arguments["path_parameters"]["run_id"])
            require_committed_call(record, response, arguments, events)
            self.placement.completed(record)
        except Exception as error:
            # Fixed bounded classification, never provider text/headers/secrets.
            self.failure = type(error).__name__[:80]
        return response


SYNTHETIC_PUBLIC_ADDRESS = "8.8.8.8"


class SyntheticIngressAddressResolver:
    """Exact fixture address selection; the returned public address is not dialled."""
    def __init__(self, hostname):
        self.hostname = hostname

    async def resolve(self, hostname):
        if hostname != self.hostname:
            raise FixtureBoundaryFailure("synthetic ingress hostname differs")
        return (SYNTHETIC_PUBLIC_ADDRESS,)


class InstalledGatewaySocketTransport(httpx.AsyncBaseTransport):
    """Validate the original synthetic destination, then use one real socket."""
    def __init__(self, hostname, target_for, endpoint_for, *, transport_factory=None):
        self.hostname, self.target_for, self.endpoint_for = hostname, target_for, endpoint_for
        self.transport_factory = transport_factory or (
            lambda: httpx.AsyncHTTPTransport(retries=0, trust_env=False))
        self._transport = None

    async def handle_async_request(self, request):
        expected_paths = {"/cpk/health/liveness", "/cpk/health/readiness"}
        if (request.method != "POST" or request.url.scheme != "https"
                or request.url.host != SYNTHETIC_PUBLIC_ADDRESS or request.url.port != 443
                or request.url.path not in expected_paths or request.url.query
                or request.headers.get("host") != self.hostname + ":443"
                or request.extensions.get("sni_hostname") != self.hostname
                or not request.headers.get("authorization", "").startswith("Bearer ")):
            raise FixtureBoundaryFailure("synthetic ingress destination differs")
        body = await request.aread()
        if len(body) > 16384:
            raise FixtureBoundaryFailure("signed ingress request exceeds bound")
        value = json.loads(body)
        if (type(value) is not dict or set(value) != {
                "profile", "target_id", "attempt_id", "request", "workload_credential"}
                or value["profile"] != "cpk-gateway-health-relay-request.v2"
                or value["request"] != self.target_for(value["target_id"], value["request"])
                or request.url.path != "/cpk/health/" + value["request"]["kind"]):
            raise FixtureBoundaryFailure("signed ingress target differs")
        origin = self.endpoint_for(value["request"])
        url = httpx.URL(origin)
        if url.scheme != "http" or url.path not in ("", "/") or url.query or url.userinfo:
            raise FixtureBoundaryFailure("installed gateway origin differs")
        forwarded = httpx.Request(request.method, str(url).rstrip("/") + request.url.path,
            headers=request.headers, content=body,
            extensions={key: value for key, value in request.extensions.items() if key != "sni_hostname"})
        self._transport = self.transport_factory()
        return await self._transport.handle_async_request(forwarded)

    async def aclose(self):
        if self._transport is not None:
            await self._transport.aclose()
            self._transport = None
