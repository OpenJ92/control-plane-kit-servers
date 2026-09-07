"""Interpret catalogue intent through the maintained client's public transport."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .journal import JournalError, canonical_operation_ref
from .transport import ClientAuthorizationError, ClientTransportError
from .workflow import ClientInputError, MAXIMUM_CURSOR_BYTES, _read_desired

SCHEMA = "cpk.client-catalogue-invocation.v1"
MAXIMUM_INTEGER = 2**63 - 1
SESSION_STATES = {"open", "closed", "cancelled"}
RUN_STATES = {"claimed", "running", "paused", "succeeded", "failed", "compensating",
              "compensated", "partially_failed", "uncompensated_failure", "cancelled"}
SELECTION_STATES = {"none", "selected", "ambiguous", "unavailable"}
ROUTES = {kind: "command.desired-topology-draft." + kind for kind in ("create", "revise", "select")}
ACTION_SCOPES = {
    "command.deployment.prepare": (("instance:workspace:edit", "plan:request"),),
    "command.approval.decide": (("plan:approve",), ("plan:approve-destructive",)),
    "command.run.start": (("execution:operate",),),
    "command.deployment.execute": (("execution:operate",),),
    "command.graph.advance-current": (("execution:operate",),),
}


def fail():
    raise ClientInputError("catalogue input or public evidence is invalid")


def obj(value, keys=None):
    if not isinstance(value, dict) or (keys is not None and set(value) != set(keys)):
        fail()
    return value


def text(value, maximum=512):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        fail()
    return value


def integer(value, minimum=1, maximum=MAXIMUM_INTEGER):
    if type(value) is not int or not minimum <= value <= maximum:
        fail()
    return value


def domain(value, values):
    if not isinstance(value, str) or value not in values:
        fail()
    return value


def boolean(value):
    if type(value) is not bool:
        fail()
    return value


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _bounded_json(value, maximum):
    try:
        encoded = json.dumps(value, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise ClientInputError("catalogue JSON is invalid") from None
    if len(encoded) > maximum:
        raise ClientInputError("catalogue JSON exceeds its bound")
    return encoded


def hash_text(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        fail()
    return value


def revision(value):
    value = obj(value, {"draft_id", "revision", "graph_id"})
    return {"draft_id": text(value["draft_id"]), "revision": integer(value["revision"]), "graph_id": text(value["graph_id"])}


@dataclass(frozen=True)
class CatalogueResult:
    """A transport receipt or safe public observation; never deployment truth."""
    value: dict

    def descriptor(self):
        return json.loads(_bounded_json(self.value, 1048576))

    @property
    def status(self):
        return self.value.get("status", "observed")

    @property
    def operation_ref(self):
        return self.value.get("operation_ref")

    @property
    def exit_code(self):
        return 4 if self.status == "attention-required" else 0


def _result(record, *, attention=False):
    start = record["start_response"] or {}
    response = record["draft_response"]
    selected = None
    if response is not None and record["intent"]["kind"] == "select":
        selected = {name: response[name] for name in ("desired_realized_projection_id", "desired_graph_revision")}
    return CatalogueResult({
        "schema": "cpk.client-catalogue-result.v1", "operation_ref": record["operation_ref"],
        "operation": record["intent"]["kind"], "status": "attention-required" if attention else "recorded",
        "workspace_id": record["target"]["workspace_id"], "session_id": start.get("session_id"),
        "start_action_id": start.get("start_action_id"),
        "revision": None if response is None else {name: response[name] for name in ("draft_id", "revision", "graph_id")},
        "selection": selected, "next_public_read": ("read.session-detail" if start else "read.workspace") if attention else None})


def _source(value):
    value = obj(value, {"path", "size", "sha256"})
    if not Path(text(value["path"], 4096)).is_absolute():
        fail()
    integer(value["size"], 0, 65536)
    hash_text(value["sha256"])


def _intent(value):
    value = obj(value)
    kind = domain(value.get("kind"), ROUTES)
    canonical_operation_ref(value.get("idempotency_key"))
    expected = {"kind", "idempotency_key"}
    if kind in {"create", "revise"}:
        expected.add("source")
        _source(value.get("source"))
    if kind == "create":
        expected.add("title")
        if value.get("title") is not None:
            text(value["title"])
    elif kind == "revise":
        expected.update({"draft_id", "expected_head_revision"})
        text(value.get("draft_id"))
        integer(value.get("expected_head_revision"), maximum=MAXIMUM_INTEGER - 1)
    else:
        expected.update({"draft_id", "revision", "expected_desired_graph_id", "expected_desired_realized_projection_id", "expected_desired_graph_revision"})
        text(value.get("draft_id"))
        integer(value.get("revision"))
        integer(value.get("expected_desired_graph_revision"), 0, MAXIMUM_INTEGER - 1)
        _pair(value.get("expected_desired_graph_id"), value.get("expected_desired_realized_projection_id"))
    obj(value, expected)


def _pair(graph, projection):
    if (graph is None) != (projection is None):
        fail()
    if graph is not None:
        text(graph)
        text(projection)


def _request_body(record, graph=None):
    intent = record["intent"]
    result = {"session_id": record["start_response"]["session_id"], "idempotency_key": intent["idempotency_key"]}
    if intent["kind"] in {"create", "revise"}:
        result["graph"] = graph
        if intent["kind"] == "create":
            if intent["title"] is not None:
                result["title"] = intent["title"]
        else:
            result["expected_head_revision"] = intent["expected_head_revision"]
    else:
        for name in ("revision", "expected_desired_graph_id", "expected_desired_realized_projection_id", "expected_desired_graph_revision"):
            result[name] = intent[name]
    return result


def _response(value, record):
    intent = record["intent"]
    keys = {"workspace_id", "draft_id", "revision", "graph_id"}
    if intent["kind"] == "select":
        keys.update({"desired_realized_projection_id", "desired_graph_revision"})
    value = obj(value, keys)
    if value["workspace_id"] != record["target"]["workspace_id"]:
        fail()
    text(value["draft_id"])
    text(value["graph_id"])
    integer(value["revision"])
    if intent["kind"] == "create":
        if value["revision"] != 1:
            fail()
    elif value["draft_id"] != intent["draft_id"]:
        fail()
    if intent["kind"] == "revise" and value["revision"] != intent["expected_head_revision"] + 1:
        fail()
    if intent["kind"] == "select":
        text(value["desired_realized_projection_id"])
        integer(value["desired_graph_revision"])
        if value["revision"] != intent["revision"] or value["desired_graph_revision"] != intent["expected_desired_graph_revision"] + 1:
            fail()
    return dict(value)


def validate_journal(value, operation_ref):
    """Validate only the concrete catalogue record; deployment v1 stays separate."""
    try:
        obj(value, {"schema", "operation_ref", "target", "intent", "start_request", "start_response", "draft_request", "draft_response", "last_result"})
        if value["schema"] != SCHEMA or value["operation_ref"] != operation_ref:
            fail()
        canonical_operation_ref(operation_ref)
        target = obj(value["target"], {"endpoint_sha256", "workspace_id"})
        hash_text(target["endpoint_sha256"])
        text(target["workspace_id"])
        _intent(value["intent"])
        start = obj(value["start_request"], {"idempotency_key", "title"})
        canonical_operation_ref(start["idempotency_key"])
        if start["title"] != "Catalogue " + value["intent"]["kind"] or start["idempotency_key"] == value["intent"]["idempotency_key"]:
            fail()
        response = value["start_response"]
        if response is not None:
            obj(response, {"session_id", "start_action_id"})
            text(response["session_id"])
            text(response["start_action_id"])
        pending = value["draft_request"]
        if pending is not None:
            obj(pending, {"route_id", "session_id", "idempotency_key", "body_sha256"})
            if response is None or pending["session_id"] != response["session_id"] or pending["route_id"] != ROUTES[value["intent"]["kind"]] or pending["idempotency_key"] != value["intent"]["idempotency_key"]:
                fail()
            hash_text(pending["body_sha256"])
            if value["intent"]["kind"] == "select" and digest(_request_body(value)) != pending["body_sha256"]:
                fail()
        if value["draft_response"] is not None:
            if pending is None:
                fail()
            _response(value["draft_response"], value)
        result = value["last_result"]
        if result is not None:
            if result not in (_result(value).descriptor(), _result(value, attention=True).descriptor()):
                fail()
            if result["status"] == "recorded" and value["draft_response"] is None:
                fail()
    except (ClientInputError, KeyError, TypeError, ValueError, RecursionError) as error:
        raise JournalError("catalogue journal is invalid") from error


def _call(client, route, *, path=None, body=None):
    return client.transport.call(route, path_parameters=path or {"workspace_id": client.profile.workspace_id}, payload=body or {}, credential_role="operator")


def _resume(client, record):
    if record["draft_response"] is not None:
        return _result(record)
    try:
        if record["start_response"] is None:
            request = {"workspace_id": client.profile.workspace_id, **record["start_request"], "metadata": {}}
            response = obj(_call(client, "command.operation-session.start", body=request))
            text(response.get("session_id"))
            text(response.get("action_id"))
            if response.get("action_type") != "start-operation-session" or type(response.get("ordinal")) is not int or response["ordinal"] != 1:
                fail()
            domain(response.get("status"), SESSION_STATES)
            boolean(response.get("replayed"))
            record["start_response"] = {"session_id": response["session_id"], "start_action_id": response["action_id"]}
            record["last_result"] = None
            client.journal.write(record["operation_ref"], record)
        session_id = record["start_response"]["session_id"]
        graph = None
        if "source" in record["intent"]:
            source, graph = _read_desired(Path(record["intent"]["source"]["path"]))
            if source != record["intent"]["source"]:
                fail()
        body = _request_body(record, graph)
        body_sha = digest(body)
        if len(json.dumps(body, separators=(",", ":")).encode()) > 65536:
            fail()
        if record["draft_request"] is None:
            detail = obj(_call(client, "read.session-detail", path={"workspace_id": client.profile.workspace_id, "session_id": session_id}))
            session = obj(detail.get("session"))
            if session.get("workspace_id") != client.profile.workspace_id or session.get("session_id") != session_id or session.get("status") != "open":
                fail()
            record["draft_request"] = {"route_id": ROUTES[record["intent"]["kind"]], "session_id": session_id,
                "idempotency_key": record["intent"]["idempotency_key"], "body_sha256": body_sha}
            record["last_result"] = None
            client.journal.write(record["operation_ref"], record)
        elif record["draft_request"]["body_sha256"] != body_sha:
            fail()
        path = {"workspace_id": client.profile.workspace_id}
        if record["intent"]["kind"] != "create":
            path["draft_id"] = record["intent"]["draft_id"]
        response = _call(client, record["draft_request"]["route_id"], path=path, body=body)
        record["draft_response"] = _response(response, record)
        record["last_result"] = None
        client.journal.write(record["operation_ref"], record)
    except ClientAuthorizationError:
        raise
    except (ClientTransportError, ClientInputError):
        result = _result(record, attention=True)
        record["last_result"] = result.descriptor()
        client.journal.write(record["operation_ref"], record)
        return result
    result = _result(record)
    record["last_result"] = result.descriptor()
    client.journal.write(record["operation_ref"], record)
    return result


def mutate(client, kind, *, path=None, title=None, draft_id=None, expected_head_revision=None, revision_number=None):
    intent = {"kind": kind, "idempotency_key": client._new_key()}
    if kind in {"create", "revise"}:
        source, graph = _read_desired(path)
        intent["source"] = source
    if kind == "create":
        intent["title"] = title
    elif kind == "revise":
        intent.update(draft_id=draft_id, expected_head_revision=expected_head_revision)
    else:
        text(draft_id)
        integer(revision_number)
        workspace = obj(obj(_call(client, "read.workspace")).get("workspace"))
        if workspace.get("workspace_id") != client.profile.workspace_id:
            fail()
        intent.update(draft_id=draft_id, revision=revision_number,
            expected_desired_graph_id=workspace.get("desired_graph_id"),
            expected_desired_realized_projection_id=workspace.get("desired_realized_projection_id"),
            expected_desired_graph_revision=workspace.get("desired_graph_revision"))
    _intent(intent)
    operation_ref = canonical_operation_ref(client._identity_factory())
    record = {"schema": SCHEMA, "operation_ref": operation_ref,
        "target": {"endpoint_sha256": client.profile.target_digest, "workspace_id": client.profile.workspace_id},
        "intent": intent, "start_request": {"idempotency_key": client._new_key(), "title": "Catalogue " + kind},
        "start_response": None, "draft_request": None, "draft_response": None, "last_result": None}
    with client.journal.mutation_lock(operation_ref):
        client.journal.create(operation_ref, record)
        return _resume(client, record)


def resume(client, operation_ref):
    operation_ref = canonical_operation_ref(operation_ref)
    with client.journal.mutation_lock(operation_ref):
        record = client.journal.read(operation_ref)
        if record.get("schema") != SCHEMA or record["target"] != {"endpoint_sha256": client.profile.target_digest, "workspace_id": client.profile.workspace_id}:
            raise ClientInputError("catalogue operation target is invalid")
        return _resume(client, record)


def _overview(value):
    graphs = obj(value.get("graphs"))
    pointers = {}
    for name in ("current", "desired"):
        source = obj(graphs.get(name))
        assigned = boolean(source.get("assigned"))
        graph, projection = source.get("graph_id"), source.get("realized_projection_id")
        _pair(graph, projection)
        if assigned != (graph is not None):
            fail()
        pointers[name] = {"assigned": assigned, "graph_id": graph, "realized_projection_id": projection}
    relation = domain(graphs.get("relation"), {"unassigned", "converged", "diverged", "unavailable"})
    desired = obj(graphs["desired"])
    generation = desired.get("revision")
    if generation is not None:
        integer(generation, 0)
    elif relation != "unavailable":
        fail()
    pointers["desired"]["revision"] = generation
    equal = pointers["current"]["graph_id"] == pointers["desired"]["graph_id"] and pointers["current"]["realized_projection_id"] == pointers["desired"]["realized_projection_id"]
    if relation == "unassigned" and pointers["desired"]["assigned"]:
        fail()
    if relation == "converged" and (not pointers["desired"]["assigned"] or not equal):
        fail()
    if relation == "diverged" and (not pointers["desired"]["assigned"] or equal):
        fail()
    navigation = obj(desired.get("draft"), {"state", "selected", "head"})
    state = domain(navigation["state"], {"none", "selected", "unavailable"})
    selected = head = None
    if state == "selected":
        selected, head = revision(navigation["selected"]), revision(navigation["head"])
        if selected["draft_id"] != head["draft_id"] or head["revision"] < selected["revision"] or selected["graph_id"] != pointers["desired"]["graph_id"]:
            fail()
    elif navigation["selected"] is not None or navigation["head"] is not None:
        fail()
    pointers["desired"]["draft"] = {"state": state, "selected": selected, "head": head}
    pointers["relation"] = relation
    source = obj(value.get("workflow"))
    selection = domain(source.get("selection"), SELECTION_STATES)
    workflow = {"selection": selection}
    for name, identity, statuses in (("session", "session_id", {"open"}), ("plan", "plan_id", {"planned"})):
        item = source.get(name)
        if item is None:
            if selection == "selected":
                fail()
            workflow[name] = None
        else:
            if selection != "selected":
                fail()
            item = obj(item)
            workflow[name] = {identity: text(item.get(identity)), "status": domain(item.get("status"), statuses)}
    approval = source.get("approval")
    if approval is not None:
        if selection != "selected":
            fail()
        approval = obj(approval)
        scope = domain(approval.get("required_scope"), {"plan:approve", "plan:approve-destructive"})
        destructive = boolean(approval.get("destructive"))
        if destructive != (scope == "plan:approve-destructive"):
            fail()
        approval = {"request_id": text(approval.get("request_id")), "state": domain(approval.get("state"), {"pending"}),
                    "required_scope": scope, "destructive": destructive}
    workflow["approval"] = approval
    run_selection = domain(source.get("run_selection"), SELECTION_STATES)
    run = source.get("run")
    if run_selection == "selected":
        if selection != "selected":
            fail()
        run = obj(run)
        run = {"run_id": text(run.get("run_id")), "request_id": text(run.get("request_id")),
               "status": domain(run.get("status"), RUN_STATES), "attempt": integer(run.get("attempt"))}
    elif run is not None:
        fail()
    if selection != "selected" and run_selection != ("none" if selection == "none" else "unavailable"):
        fail()
    workflow.update(run_selection=run_selection, run=run)
    prepared = obj(source.get("prepared_draft"), {"state", "revision"})
    prepared_state = domain(prepared["state"], {"none", "prepared", "unavailable"})
    prepared_revision = None
    if prepared_state == "prepared":
        prepared_revision = revision(prepared["revision"])
        if selection != "selected" or prepared_revision["graph_id"] != pointers["desired"]["graph_id"]:
            fail()
    elif prepared["revision"] is not None:
        fail()
    if selection != "selected" and prepared_state != ("none" if selection == "none" else "unavailable"):
        fail()
    workflow["prepared_draft"] = {"state": prepared_state, "revision": prepared_revision}
    action = obj(value.get("next_action"))
    action_state = domain(action.get("state"), {"none", "available", "ambiguous", "unavailable"})
    operation, scopes = action.get("operation_id"), action.get("required_scopes")
    if not isinstance(scopes, list):
        fail()
    if action_state == "available":
        domain(operation, ACTION_SCOPES)
        if tuple(scopes) not in ACTION_SCOPES[operation]:
            fail()
    elif operation is not None or scopes:
        fail()
    return {"graphs": pointers, "workflow": workflow, "next_action": {"state": action_state, "operation_id": operation, "required_scopes": list(scopes)}}


def read(client, kind, *, draft_id=None, revision_number=None, limit=50, cursor=None):
    path = {"workspace_id": client.profile.workspace_id}
    payload = {}
    if kind == "overview":
        route = "read.operator-overview"
    elif kind == "draft-list":
        integer(limit, 1, 100)
        route = "read.desired-topology-drafts"
        payload = {"limit": limit}
        if cursor is not None:
            obj(cursor)
            _bounded_json(cursor, MAXIMUM_CURSOR_BYTES)
            payload["after"] = cursor
    else:
        text(draft_id)
        integer(revision_number)
        route = "read.desired-topology-draft-revision"
        path.update(draft_id=draft_id, revision=str(revision_number))
    value = obj(_call(client, route, path=path, body=payload))
    if value.get("workspace_id") != client.profile.workspace_id:
        fail()
    next_cursor = None
    if kind == "overview":
        if value.get("kind") != "operator-overview":
            fail()
        observation = _overview(value)
    elif kind == "draft-list":
        if value.get("kind") != "desired-topology-drafts" or value.get("limit") != limit:
            fail()
        items = value.get("items")
        if not isinstance(items, list) or len(items) > limit:
            fail()
        observation = []
        for item in items:
            obj(item)
            if item.get("workspace_id") != client.profile.workspace_id:
                fail()
            deleted = item.get("deleted_at")
            if deleted is not None:
                text(deleted, 128)
            observation.append({"draft_id": text(item.get("draft_id")), "head_revision": integer(item.get("head_revision")), "deleted_at": deleted})
        next_cursor = value.get("next_cursor")
        if next_cursor is not None:
            obj(next_cursor)
            _bounded_json(next_cursor, MAXIMUM_CURSOR_BYTES)
    else:
        if value.get("kind") != "desired-topology-draft-revision" or value.get("draft_id") != draft_id or type(value.get("revision")) is not int or value["revision"] != revision_number:
            fail()
        observation = {"draft_id": draft_id, "revision": revision_number, "graph_id": text(value.get("graph_id")), "created_at": text(value.get("created_at"), 128)}
    result = {"schema": "cpk.client-catalogue-read.v1", "kind": kind, "workspace_id": client.profile.workspace_id,
              "observation": observation, "next_cursor": next_cursor}
    _bounded_json(result, 1048576)
    return CatalogueResult(result)
