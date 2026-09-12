"""Finite public evidence composition; never workflow or provider authority."""
from __future__ import annotations

from dataclasses import dataclass
import json
from time import monotonic

from control_plane_kit_core.operations.lifecycle import ActivityEventKind, ActivityRunStatus

from .catalogue import _bounded_json, _overview, domain, integer, obj, text
from .journal import JOURNAL_SCHEMA, SAVED_JOURNAL_SCHEMA, JournalError, canonical_operation_ref
from .transport import ClientAuthorizationError, ClientTransportError
from .workflow import ClientInputError

LIMITS = {"operations": 4, "calls": 32, "pages_per_collection": 1, "runs_per_plan": 2,
          "events_per_run": 10, "scheduling_seconds": 60, "output_bytes": 262144}
READS = frozenset({"read.plan-detail", "read.session-detail", "read.approval-detail",
                  "read.desired-topology-draft-revision", "read.plan-runs", "read.run-events",
                  "read.operator-overview"})
PLAN_FIELDS = ("plan_id", "session_id", "base_graph_id", "base_realized_projection_id",
               "desired_graph_id", "desired_realized_projection_id")
METADATA_FIELDS = {"source": "deployment_prepare_source", "draft_id": "deployment_prepare_saved_draft_id",
                   "revision": "deployment_prepare_saved_revision", "graph_id": "deployment_prepare_saved_graph_id"}


class _Budget(Exception):
    pass


class _Mismatch(Exception):
    pass


def _section(state="not-applicable", data=None):
    return {"state": state, "data": data}


@dataclass(frozen=True)
class ReportResult:
    value: dict

    def descriptor(self):
        return json.loads(_bounded_json(self.value, LIMITS["output_bytes"]))

    @property
    def status(self):
        return self.value["status"]

    @property
    def exit_code(self):
        return 0 if self.status == "observed" else 4


class _Reader:
    def __init__(self, client):
        self.client = client
        self.started = monotonic()
        self.calls = 0

    def read(self, route, *, path=None, payload=None):
        if route not in READS:
            raise ClientInputError("report read is invalid")
        if self.calls >= LIMITS["calls"] or monotonic() - self.started >= LIMITS["scheduling_seconds"]:
            raise _Budget
        self.calls += 1
        value = self.client.transport.call(route,
            path_parameters={"workspace_id": self.client.profile.workspace_id, **(path or {})},
            payload=payload or {}, credential_role="operator")
        obj(value)
        _bounded_json(value, 1048576)
        if value.get("workspace_id") != self.client.profile.workspace_id:
            raise _Mismatch
        return value

    def detail(self, route, key, identity, expected):
        value = self.read(route, path={identity: expected})
        if value.get("kind") != route.removeprefix("read."):
            raise ClientInputError("report detail is invalid")
        item = obj(value.get(key))
        if item.get(identity) != expected:
            raise _Mismatch
        return item

    def page(self, route, identity, expected, limit):
        value = self.read(route, path={identity: expected}, payload={"limit": limit})
        if value.get("kind") != route.removeprefix("read.") or type(value.get("limit")) is not int or value["limit"] != limit:
            raise ClientInputError("report page is invalid")
        items = value.get("items")
        if not isinstance(items, list) or len(items) > limit or "next_cursor" not in value:
            raise ClientInputError("report page is invalid")
        cursor = value["next_cursor"]
        if cursor is not None:
            obj(cursor)
            _bounded_json(cursor, 16384)
        return items, cursor is not None


def _observe(row, name, operation):
    try:
        result = operation()
    except ClientAuthorizationError:
        raise
    except _Budget:
        result = _section("truncated")
    except _Mismatch:
        result = _section("mismatch")
    except (ClientInputError, ClientTransportError, JournalError, KeyError, TypeError, ValueError, RecursionError):
        result = _section("unavailable")
    if result["state"] in {"truncated", "mismatch", "unavailable"}:
        row["issues"].append(name + "-" + result["state"])
    return result


def _requested(journal):
    result = {"provenance": "transport-provenance", "source": "file", "kind": "prepare",
              "draft_id": None, "revision": None, "expected_head_revision": None,
              "receipt_revision": None, "expected_current": None, "expected_desired": None,
              "desired_generation": None}
    schema = journal["schema"]
    if schema == SAVED_JOURNAL_SCHEMA:
        request = journal["prepare_request"]
        result.update(source="saved", draft_id=request["draft_id"], revision=request["revision"],
                      expected_current=request["expected_current"], expected_desired=request["expected_desired"],
                      desired_generation=request["expected_desired_graph_revision"])
    elif schema != JOURNAL_SCHEMA:
        intent = journal["intent"]
        result.update(source="catalogue", kind=intent["kind"], draft_id=intent.get("draft_id"),
                      revision=intent.get("revision"), expected_head_revision=intent.get("expected_head_revision"))
        receipt = journal["draft_response"]
        if receipt is not None:
            result["receipt_revision"] = {key: receipt[key] for key in ("draft_id", "revision", "graph_id")}
    return _section("observed", result)


def _plan(reader, plan_id, session_id, requested):
    item = reader.detail("read.plan-detail", "plan", "plan_id", plan_id)
    value = {key: text(item.get(key)) for key in PLAN_FIELDS}
    value["desired_graph_revision"] = integer(item.get("desired_graph_revision"), 0)
    value["status"] = domain(item.get("status"), {"planned", "superseded", "cancelled"})
    if session_id is not None and value["session_id"] != session_id:
        raise _Mismatch
    if requested["source"] == "saved":
        pairs = (("base_graph_id", requested["expected_current"]["authored_graph_id"]),
                 ("base_realized_projection_id", requested["expected_current"]["realized_projection_id"]),
                 ("desired_graph_id", requested["expected_desired"]["authored_graph_id"]),
                 ("desired_realized_projection_id", requested["expected_desired"]["realized_projection_id"]),
                 ("desired_graph_revision", requested["desired_generation"]))
        if any(value[key] != expected for key, expected in pairs):
            raise _Mismatch
    return _section("observed", value)


def _session(reader, session_id):
    item = reader.detail("read.session-detail", "session", "session_id", session_id)
    if item.get("workspace_id") != reader.client.profile.workspace_id:
        raise _Mismatch
    metadata = obj(item.get("metadata"))
    reported = None
    if any(key in metadata for key in METADATA_FIELDS.values()):
        reported = {key: text(metadata.get(source)) for key, source in METADATA_FIELDS.items()}
        domain(reported["source"], {"saved-revision.v1"})
        revision = reported["revision"]
        if not revision.isascii() or not revision.isdigit() or revision.startswith("0") or len(revision) > 19:
            raise ClientInputError("reported metadata is invalid")
        integer(int(revision))
    return _section("observed", {"session_id": session_id,
        "status": domain(item.get("status"), {"open", "closed", "cancelled"}),
        "server_reported_saved_metadata": reported})


def _association(reader, requested, plan):
    reference = requested["receipt_revision"]
    if requested["source"] == "saved":
        reference = {"draft_id": requested["draft_id"], "revision": requested["revision"]}
    if reference is None:
        return _section()
    value = reader.read("read.desired-topology-draft-revision",
                        path={"draft_id": reference["draft_id"], "revision": str(reference["revision"])})
    if value.get("kind") != "desired-topology-draft-revision":
        raise ClientInputError("report revision is invalid")
    observed = {"draft_id": text(value.get("draft_id")), "revision": integer(value.get("revision")),
                "graph_id": text(value.get("graph_id"))}
    if any(observed[key] != reference[key] for key in reference):
        raise _Mismatch
    if plan is None:
        return _section("not-applicable", observed)
    return _section("matched" if observed["graph_id"] == plan["desired_graph_id"] else "mismatch", observed)


def _approval(reader, approval_id, plan):
    value = reader.read("read.approval-detail", path={"approval_id": approval_id})
    if value.get("kind") != "approval-detail":
        raise ClientInputError("report approval is invalid")
    item = obj(value.get("approval"))
    if item.get("request_id") != approval_id or item.get("plan_id") != plan["plan_id"] or item.get("session_id") != plan["session_id"]:
        raise _Mismatch
    destructive = item.get("destructive")
    scope = domain(item.get("required_scope"), {"plan:approve", "plan:approve-destructive"})
    if type(destructive) is not bool or destructive != (scope == "plan:approve-destructive"):
        raise ClientInputError("report approval is invalid")
    return _section("observed", {"request_id": approval_id, "plan_id": plan["plan_id"], "session_id": plan["session_id"],
        "state": domain(item.get("state"), {"pending", "approved", "rejected"}), "required_scope": scope, "destructive": destructive})


def _events(reader, run_id):
    items, truncated = reader.page("read.run-events", "run_id", run_id, LIMITS["events_per_run"])
    values = []
    for item in items:
        obj(item)
        if item.get("run_id") != run_id:
            raise _Mismatch
        activity_id = item.get("activity_id")
        values.append({"event_id": text(item.get("event_id")), "ordinal": integer(item.get("ordinal")),
                       "event_type": domain(item.get("event_type"), {value.value for value in ActivityEventKind}),
                       "activity_id": None if activity_id is None else text(activity_id)})
    if len({item["event_id"] for item in values}) != len(values) or len({item["ordinal"] for item in values}) != len(values):
        raise ClientInputError("report events are invalid")
    return _section("truncated" if truncated else "observed", values)


def _runs(reader, plan, row):
    items, truncated = reader.page("read.plan-runs", "plan_id", plan["plan_id"], LIMITS["runs_per_plan"])
    values = []
    for item in items:
        obj(item)
        if item.get("plan_id") != plan["plan_id"]:
            raise _Mismatch
        run_id = text(item.get("run_id"))
        status = domain(item.get("status"), {value.value for value in ActivityRunStatus})
        values.append({"run_id": run_id, "plan_id": plan["plan_id"], "status": status,
                       "events": _observe(row, "events", lambda: _events(reader, run_id))})
    if len({item["run_id"] for item in values}) != len(values):
        raise ClientInputError("report runs are invalid")
    return _section("truncated" if truncated else "observed", values)


def _operation(reader, operation_ref):
    row = {"operation_ref": operation_ref, "state": "observed", **{name: _section() for name in
           ("requested", "session", "association", "plan", "approval", "runs")}, "issues": []}
    try:
        journal = reader.client.journal.read(operation_ref)
        if journal["target"] != {"workspace_id": reader.client.profile.workspace_id, "endpoint_sha256": reader.client.profile.target_digest}:
            raise JournalError("report target is invalid")
    except JournalError:
        row.update(state="unavailable", issues=["journal-unavailable"])
        return row
    row["requested"] = _requested(journal)
    requested = row["requested"]["data"]
    coordinates = journal.get("coordinates", {})
    session_id = coordinates.get("session_id")
    if requested["source"] == "catalogue":
        session_id = (journal["start_response"] or {}).get("session_id")
    if coordinates.get("plan_id"):
        row["plan"] = _observe(row, "plan", lambda: _plan(reader, coordinates["plan_id"], session_id, requested))
    plan = row["plan"]["data"]
    if plan:
        session_id = plan["session_id"]
    if session_id:
        row["session"] = _observe(row, "session", lambda: _session(reader, session_id))
    row["association"] = _observe(row, "association", lambda: _association(reader, requested, plan))
    if plan:
        if coordinates.get("approval_request_id"):
            row["approval"] = _observe(row, "approval", lambda: _approval(reader, coordinates["approval_request_id"], plan))
        row["runs"] = _observe(row, "runs", lambda: _runs(reader, plan, row))
    if journal.get("pending_request") is not None or (requested["source"] == "catalogue" and journal["draft_response"] is None):
        row["issues"].append("transport-response-unresolved")
    if row["issues"]:
        row["state"] = "mismatch" if any(code.endswith("mismatch") for code in row["issues"]) else "truncated" if any(code.endswith("truncated") for code in row["issues"]) else "unavailable"
    return row


def collect(client, operation_refs):
    if not isinstance(operation_refs, (tuple, list)) or not 1 <= len(operation_refs) <= LIMITS["operations"]:
        raise ClientInputError("report operation references are invalid")
    refs = [canonical_operation_ref(value) for value in operation_refs]
    if len(set(refs)) != len(refs):
        raise ClientInputError("report operation references are invalid")
    reader = _Reader(client)
    rows = [_operation(reader, reference) for reference in refs]
    final = {"issues": []}
    def overview():
        value = reader.read("read.operator-overview")
        if value.get("kind") != "operator-overview":
            raise ClientInputError("report overview is invalid")
        return _section("observed", _overview(value))
    latest = _observe(final, "overview", overview)
    result = {"schema": "cpk.client-report.v1", "workspace_id": client.profile.workspace_id,
              "status": "attention-required" if final["issues"] or any(row["issues"] for row in rows) else "observed",
              "atomic_snapshot": False, "provider_freshness": "unknown",
              "elapsed_seconds": round(max(0, monotonic() - reader.started), 3), "limits": dict(LIMITS),
              "calls": reader.calls, "operations": rows, "latest_overview": latest}
    try:
        _bounded_json(result, LIMITS["output_bytes"])
    except ClientInputError:
        for row in rows:
            for name in ("requested", "session", "association", "plan", "approval", "runs"):
                row[name] = _section("truncated")
            row.update(state="truncated", issues=["output-truncated"])
        result.update(status="attention-required", latest_overview=_section("truncated"))
    return ReportResult(result)
