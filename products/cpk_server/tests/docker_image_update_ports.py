"""#251 fixture boundaries; CPK and Docker retain all execution semantics."""
from dataclasses import dataclass, replace
import json
import re

import httpx

from control_plane_kit_core.planning import StartNode, StartRuntime, ReconcileNode
from control_plane_kit_core.operations.lifecycle import ActivityEventKind, ActivityRunStatus, FailureCategory
from control_plane_kit_core.runtime_effects import EffectResultKind
from control_plane_kit_core.runtime_effect_observation import (
    runtime_effect_intent_for_request, runtime_effect_intent_fingerprint, runtime_effect_result_fingerprint,
)
from control_plane_kit_core.operations.recovery import (
    EffectAttemptIdentity, EffectAttemptFence, EffectAttemptState, EffectAttemptStatus,
)
from control_plane_kit_operations.effect_attempts import effect_attempt_state_fingerprint
from control_plane_kit_core.configuration_invocation import configuration_invocation_correlation_for_request
from control_plane_kit_core.configuration_installation import (
    ConfigurationInstallationDisposition, configuration_installation_receipt_for_result,
)
from control_plane_kit_interpreters.docker.configuration import _container_incarnation_fingerprint


class FixtureBoundaryFailure(RuntimeError):
    """Fatal test setup/observation failure; never a retryable HTTP failure."""


@dataclass(frozen=True)
class CompletedRuntimeCall:
    request: object
    result: object


class RecordedDockerRuntime:
    """Delegate once, retain the genuine request/result; no effect interpretation."""
    def __init__(self, runtime, resources=None):
        self.runtime = runtime
        self.resources = resources
        self.completed = []

    def execute(self, request):
        if self.resources is not None:
            self.resources.starting(request)
        result = self.runtime.execute(request)
        return self._record(request, result)

    def execute_with_authority(self, request, authority):
        if self.resources is not None:
            self.resources.starting(request)
        result = self.runtime.execute_with_authority(request, authority)
        return self._record(request, result)

    def _record(self, request, result):
        record = CompletedRuntimeCall(request, result)
        self.completed.append(record)
        if self.resources is not None:
            try:
                self.resources.observed(record)
            except Exception as error:
                self.resources.failure = type(error).__name__[:80]
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


def failed_apply_evidence(transport, workspace, result):
    """Read-only bounded classifications; never replace the primary failure."""
    def token(value):
        return value if type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", value) else None

    def domain(value, choices):
        return value if value in choices else "unclassified"

    evidence = {"docker_image_apply_failure": "evidence-unavailable",
        "fixture_boundary_failed": transport.failure is not None,
        "client_exception": result is None}
    try:
        if result is None:
            return evidence
        evidence.update({"workspace_id": token(workspace), "run_id": token(result.run_id),
            "plan_id": token(result.plan_id),
            "client_status": domain(result.status, {"attention-required", "converged", "no-changes"}),
            "execution": domain(result.execution, {"not-started", "running", "succeeded", "failed", "uncertain", "unverified"}),
            "advancement": domain(result.advancement, {"not-attempted", "advanced", "failed", "unverified", "unchanged"})})
        if evidence["run_id"] is None or evidence["plan_id"] is None:
            return evidence
        events = public_page(transport, "read.run-events", workspace, run_id=result.run_id)
        rows = []
        for event in events[-32:]:
            if event["run_id"] != result.run_id:
                raise FixtureBoundaryFailure("failure history run differs")
            failure = event.get("failure") or {}
            rows.append({"event_id": token(event.get("event_id")),
                "activity_id": token(event.get("activity_id")),
                "ordinal": event["ordinal"] if type(event.get("ordinal")) is int and 0 <= event["ordinal"] < 10**9 else None,
                "event_type": domain(event.get("event_type"), {item.value for item in ActivityEventKind}),
                "failure_category": domain(failure.get("category"), {item.value for item in FailureCategory}),
                "failure_code": token(failure.get("code")),
                "runtime_failure_code": token((failure.get("details") or {}).get("effect_outcome", {}).get("runtime_failure_code"))})
        evidence.update({"events": rows, "events_truncated": len(events) > 32,
            "docker_image_apply_failure": "events-observed-run-unavailable"})
        runs = public_page(transport, "read.plan-runs", workspace, plan_id=result.plan_id)
        selected = [run for run in runs if run["run_id"] == result.run_id and run["plan_id"] == result.plan_id]
        if len(selected) != 1:
            raise FixtureBoundaryFailure("failure run summary differs")
        evidence.update({"run_status": domain(selected[0].get("status"), {item.value for item in ActivityRunStatus}),
            "docker_image_apply_failure": "observed"})
    except Exception:
        # Public read/projection failure must not mask the original result or
        # latched fixture failure. No exception/provider text is retained.
        evidence["docker_image_apply_failure"] = "evidence-unavailable"
    try:
        if len(json.dumps(evidence).encode("utf-8")) <= 32768:
            return evidence
    except Exception:
        return {"docker_image_apply_failure": "evidence-unavailable"}
    return {"docker_image_apply_failure": "evidence-unavailable"}


def emit_failed_apply_evidence(transport, workspace, result):
    """Best-effort diagnostics, including serialization and output failures."""
    try:
        print(json.dumps(failed_apply_evidence(transport, workspace, result), sort_keys=True), flush=True)
        return True
    except Exception:
        # Reporting must never replace the original failed apply or cleanup.
        return False


def require_committed_call(record, response, arguments, events, worker_id):
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
    # Selected public events commit to the fence inside the typed state, rather
    # than exposing claim_generation directly. Use owner values/hash, no fold.
    state = EffectAttemptState(EffectAttemptIdentity(request.source.run_id, activity, 1),
        runtime_effect_intent_fingerprint(runtime_effect_intent_for_request(request)),
        EffectAttemptFence(worker_id, body["claim_generation"]), EffectAttemptStatus.STARTED)
    succeeded = replace(state, status=EffectAttemptStatus.SUCCEEDED,
        outcome_fingerprint=runtime_effect_result_fingerprint(result))
    for event, expected in ((starts[0], state), (later[0], succeeded)):
        if event.get("payload") != {"effect_attempt": {
                "attempt": 1, "state_fingerprint": effect_attempt_state_fingerprint(expected)}}:
            raise FixtureBoundaryFailure("public event fence or outcome commitment differs")
    return starts[0], later[0]


def require_replacement_receipt(record, prior_id, current_id):
    receipt = configuration_installation_receipt_for_result(
        configuration_invocation_correlation_for_request(record.request), record.result)
    if (receipt is None or receipt.disposition is not ConfigurationInstallationDisposition.REPLACED
            or receipt.prior_realization_fingerprint != _container_incarnation_fingerprint(prior_id)
            or receipt.current_realization_fingerprint != _container_incarnation_fingerprint(current_id)):
        raise FixtureBoundaryFailure("replacement receipt does not identify observed containers")
    return receipt


class AttachedPublicTransport:
    """Observe a genuine public response, attach the declared fixture, return it.

    A post-response hook fault is latched so the successful response reaches the
    normal client journal. The next mutation is refused before HTTP dispatch;
    the witness also calls require_healthy after apply returns.
    """
    def __init__(self, inner, runtime, placement, worker_id):
        self.inner, self.runtime, self.placement = inner, runtime, placement
        self.worker_id = worker_id
        self.failure = None
        self.unsent = []
        self.responses = []
        self.preparations = []
        self.committed = {}
        self.committed_observer = None

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
        if not completed or response.get("coordinator_status") not in {"progressed", "completed"}:
            return response
        try:
            if len(completed) != 1:
                raise FixtureBoundaryFailure("public call did not contain one runtime effect")
            record = completed[0]
            events = public_page(self.inner, "read.run-events",
                arguments["path_parameters"]["workspace_id"],
                run_id=arguments["path_parameters"]["run_id"])
            require_committed_call(record, response, arguments, events, self.worker_id)
            self.committed[record.request.effect_id] = (arguments, response)
            self.placement.require_healthy()
            if (type(record.request.operation) in (StartRuntime, StartNode)
                    or type(record.request.operation) is ReconcileNode
                    and record.request.operation.target.node_id == "gateway"):
                self.placement.completed(record)
            if self.committed_observer is not None:
                self.committed_observer(record, response)
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
        self.observations = []

    async def handle_async_request(self, request):
        expected_paths = {"/cpk/health/liveness", "/cpk/health/readiness"}
        if (request.method != "POST" or request.url.scheme != "https"
                or request.url.host != SYNTHETIC_PUBLIC_ADDRESS or request.url.port not in (None, 443)
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
        response = await self._transport.handle_async_request(forwarded)
        self.observations.append((value["target_id"], value["request"]["kind"], response.status_code))
        return response

    async def aclose(self):
        if self._transport is not None:
            await self._transport.aclose()
            self._transport = None
