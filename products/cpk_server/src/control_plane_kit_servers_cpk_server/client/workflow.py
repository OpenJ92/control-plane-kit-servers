"""Plan, apply, and observe topology through public cpk-server HTTP routes."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Callable, Mapping, Protocol
from uuid import uuid4

from .journal import (
    JOURNAL_SCHEMA,
    MAXIMUM_REQUEST_RECORDS,
    JournalError,
    JournalStore,
    canonical_operation_ref,
)
from .profile import ClientProfile
from .transport import (
    ClientAuthorizationError,
    ClientTransportError,
    PublicHttpTransport,
)


RESULT_SCHEMA = "cpk.client-result.v1"
MAXIMUM_DESIRED_BYTES = 65_536
MAXIMUM_PUBLIC_PAGES = 16
MAXIMUM_PAGE_ITEMS = 100
MAXIMUM_CURSOR_BYTES = 16_384
ATTENTION_STATUSES = frozenset({"blocked", "failed", "unsupported", "uncertain", "in-flight"})


class PublicTransport(Protocol):
    def call(
        self,
        route_id: str,
        *,
        path_parameters: Mapping[str, str],
        payload: Mapping[str, object],
        credential_role: str,
    ) -> dict[str, object]:
        ...


class ClientInputError(ValueError):
    """Fixed local input failure."""


@dataclass(frozen=True, slots=True)
class ClientResult:
    status: str
    operation_ref: str
    workspace_id: str
    plan_id: str | None = None
    approval_request_id: str | None = None
    run_id: str | None = None
    execution: str = "not-started"
    advancement: str = "not-attempted"
    health: str = "unknown"
    freshness: str = "unknown"
    required_scope: str | None = None
    destructive: bool | None = None
    changes: tuple[Mapping[str, object], ...] = ()
    next_command: str | None = None
    next_public_read: str | None = None

    def descriptor(self) -> dict[str, object]:
        value: dict[str, object] = {
            "schema": RESULT_SCHEMA,
            "status": self.status,
            "operation_ref": self.operation_ref,
            "workspace_id": self.workspace_id,
            "execution": self.execution,
            "advancement": self.advancement,
            "observation": {"health": self.health, "freshness": self.freshness},
            "changes": [dict(item) for item in self.changes],
            "next": {
                key: item
                for key, item in (
                    ("command", self.next_command),
                    ("public_read", self.next_public_read),
                )
                if item is not None
            },
        }
        for key, item in (
            ("plan_id", self.plan_id),
            ("approval_request_id", self.approval_request_id),
            ("run_id", self.run_id),
            ("required_scope", self.required_scope),
            ("destructive", self.destructive),
        ):
            if item is not None:
                value[key] = item
        return value

    @property
    def exit_code(self) -> int:
        return 4 if self.status == "attention-required" else 0


class TopologyClient:
    """Sequence existing public commands without owning deployment semantics."""

    def __init__(
        self,
        profile: ClientProfile,
        *,
        transport: PublicTransport | None = None,
        journal: JournalStore | None = None,
        identity_factory: Callable[[], str] | None = None,
    ) -> None:
        self.profile = profile
        self.transport = transport or PublicHttpTransport(profile)
        self.journal = journal or JournalStore(profile.state_directory)
        self._identity_factory = identity_factory or (lambda: str(uuid4()))

    def plan(self, desired_path: Path, *, title: str = "Topology deployment") -> ClientResult:
        source, desired = _read_desired(desired_path)
        operation_ref = canonical_operation_ref(self._identity_factory())
        workspace = self._workspace()
        current = _pointer(workspace, "current")
        if current is None:
            raise ClientInputError("workspace has no current graph")
        body = {
            "desired_graph": desired,
            "expected_current": current,
            "expected_desired": _pointer(workspace, "desired"),
            "expected_desired_graph_revision": _integer(
                workspace, "desired_graph_revision", minimum=0
            ),
            "title": _bounded_text(title, "title", 512),
            "idempotency_key": self._new_key(),
        }
        journal = _new_journal(self.profile, operation_ref, source)
        with self.journal.mutation_lock(operation_ref):
            self.journal.create(operation_ref, journal)
            result = self._mutate(
                journal,
                route_id="command.deployment.prepare",
                path_parameters={"workspace_id": self.profile.workspace_id},
                body=body,
                credential_role="operator",
                desired_source=source,
            )
            if isinstance(result, ClientResult):
                return result
            return self._finish_prepare(journal, result)

    def resume_prepare(self, operation_ref: str) -> ClientResult:
        operation_ref = canonical_operation_ref(operation_ref)
        with self.journal.mutation_lock(operation_ref):
            journal = self._load(operation_ref)
            pending = journal["pending_request"]
            if (
                not isinstance(pending, dict)
                or pending.get("route_id") != "command.deployment.prepare"
            ):
                raise ClientInputError("operation has no pending prepare request")
            result = self._replay_pending(journal)
            if isinstance(result, ClientResult):
                return result
            return self._finish_prepare(journal, result)

    def apply(
        self,
        operation_ref: str,
        *,
        execute_plan: str,
        approve_plan: str | None = None,
        approve_destructive_plan: str | None = None,
    ) -> ClientResult:
        operation_ref = canonical_operation_ref(operation_ref)
        if not execute_plan:
            raise ClientInputError("exact plan execution confirmation is required")
        with self.journal.mutation_lock(operation_ref):
            journal = self._load(operation_ref)
            pending = journal["pending_request"]
            pending_route = (
                pending.get("route_id") if isinstance(pending, dict) else None
            )
            if pending_route == "command.deployment.prepare":
                raise ClientInputError("pending preparation must be resumed with plan")
            coordinates = _coordinates(journal)
            plan_id = _coordinate(coordinates, "plan_id")
            if execute_plan != plan_id:
                raise ClientInputError("execution confirmation does not match the prepared plan")
            try:
                plan = self._plan_detail(plan_id)
                self._validate_plan(journal, plan)
            except ClientAuthorizationError:
                raise
            except (ClientInputError, ClientTransportError):
                return self._attention(
                    journal,
                    execution="unverified",
                    next_public_read="read.plan-detail",
                )
            if "session_id" not in coordinates:
                _record_plan_coordinates(coordinates, plan)
                self.journal.write(operation_ref, journal)
            approval_id = coordinates.get("approval_request_id")
            approval_pending = False
            if approval_id is not None:
                try:
                    approval = self._approval_detail(_text_coordinate(approval_id))
                    self._validate_approval(
                        plan,
                        _text_coordinate(approval_id),
                        approval,
                    )
                except ClientAuthorizationError:
                    raise
                except (ClientInputError, ClientTransportError):
                    return self._attention(
                        journal,
                        execution="unverified",
                        next_public_read="read.approval-detail",
                    )
                if approval.get("state") == "pending":
                    approval_pending = True
                    destructive = _boolean(approval, "destructive")
                    supplied = approve_destructive_plan if destructive else approve_plan
                    if supplied != plan_id:
                        raise ClientInputError("exact plan approval is required")
                    wrong = approve_plan if destructive else approve_destructive_plan
                    if wrong is not None:
                        raise ClientInputError("approval kind does not match the plan")
                    if pending_route not in {None, "command.approval.decide"}:
                        return self._attention(
                            journal,
                            next_public_read="read.approval-detail",
                        )
                elif approval.get("state") != "approved":
                    return self._attention(
                        journal,
                        next_public_read="read.approval-detail",
                    )
            if "run_id" in coordinates:
                observed_progress = self._public_status(journal)
                if pending is None and observed_progress.status == "attention-required":
                    return observed_progress
                if journal["phase"] in {"executed", "advanced", "converged"}:
                    if observed_progress.execution != "succeeded":
                        return self._attention(
                            journal,
                            execution="unverified",
                            next_public_read="read.plan-runs",
                        )
                if journal["phase"] in {"advanced", "converged"}:
                    if observed_progress.advancement != "advanced":
                        return self._attention(
                            journal,
                            execution="succeeded",
                            advancement="unverified",
                            next_public_read="read.current-graph",
                        )
            if pending is not None:
                recovered = self._replay_pending(journal)
                if isinstance(recovered, ClientResult):
                    return recovered
            if journal["phase"] == "no-changes":
                return self._status_from_journal(journal)
            if journal["phase"] == "attention-required":
                return self._status_from_journal(journal, attention=True)
            if approval_pending and pending_route is None:
                if approval_id is None:
                    raise JournalError("approval coordinate is missing")
                decided = self._mutate(
                    journal,
                    route_id="command.approval.decide",
                    path_parameters={
                        "workspace_id": self.profile.workspace_id,
                        "approval_id": _text_coordinate(approval_id),
                    },
                    body={
                        "session_id": _text(plan, "session_id"),
                        "decision": "approved",
                        "idempotency_key": self._new_key(),
                    },
                    credential_role="approver",
                )
                if isinstance(decided, ClientResult):
                    return decided
                if decided.get("state") != "approved":
                    return self._attention(
                        journal,
                        next_public_read="read.approval-detail",
                    )
            if "execution_request_id" not in coordinates:
                admitted = self._mutate(
                    journal,
                    route_id="command.deployment.admit",
                    path_parameters={
                        "workspace_id": self.profile.workspace_id,
                        "plan_id": plan_id,
                    },
                    body={
                        "session_id": _text(plan, "session_id"),
                        "approval_request_id": _text_coordinate(approval_id),
                        "readiness": [],
                        "idempotency_key": self._new_key(),
                    },
                    credential_role="operator",
                )
                if isinstance(admitted, ClientResult):
                    return admitted
                coordinates = _coordinates(journal)
            if "run_id" not in coordinates:
                request_id = _coordinate(coordinates, "execution_request_id")
                claimed = self._mutate(
                    journal,
                    route_id="command.run.claim",
                    path_parameters={
                        "workspace_id": self.profile.workspace_id,
                        "run_id": request_id,
                    },
                    body={"lease_duration_seconds": 1800, "idempotency_key": self._new_key()},
                    credential_role="worker",
                )
                if isinstance(claimed, ClientResult):
                    return claimed
                coordinates = _coordinates(journal)
            run_id = _coordinate(coordinates, "run_id")
            generation = _integer(coordinates, "claim_generation", minimum=1)
            if journal["phase"] in {"claimed", "prepared", "approved", "admitted"}:
                started = self._mutate(
                    journal,
                    route_id="command.run.start",
                    path_parameters={"workspace_id": self.profile.workspace_id, "run_id": run_id},
                    body={"claim_generation": generation, "idempotency_key": self._new_key()},
                    credential_role="worker",
                )
                if isinstance(started, ClientResult):
                    return started
                if started.get("run_status") != "running":
                    return self._attention(journal, next_public_read="read.plan-runs")
            if journal["phase"] not in {"executed", "advanced", "converged"}:
                for _ in range(MAXIMUM_REQUEST_RECORDS):
                    executed = self._mutate(
                        journal,
                        route_id="command.deployment.execute",
                        path_parameters={
                            "workspace_id": self.profile.workspace_id,
                            "run_id": run_id,
                        },
                        body={
                            "claim_generation": generation,
                            "max_effects": 1,
                            "idempotency_key": self._new_key(),
                        },
                        credential_role="worker",
                    )
                    if isinstance(executed, ClientResult):
                        return executed
                    status = _text(executed, "coordinator_status")
                    if status == "completed":
                        if executed.get("run_status") != "succeeded":
                            return self._attention(journal, next_public_read="read.plan-runs")
                        break
                    if status != "progressed":
                        return self._attention(
                            journal,
                            execution=(
                                "running"
                                if status == "in-flight"
                                else status
                                if status in ATTENTION_STATUSES
                                else "unverified"
                            ),
                            next_public_read="read.run-events",
                        )
                else:
                    return self._attention(
                        journal,
                        execution="running",
                        next_public_read="read.run-events",
                    )
            coordinates = _coordinates(journal)
            if journal["phase"] != "advanced":
                try:
                    current = _pointer(self._workspace(), "current")
                except ClientAuthorizationError:
                    raise
                except (ClientInputError, ClientTransportError):
                    return self._attention(
                        journal,
                        execution="succeeded",
                        advancement="unverified",
                        next_public_read="read.current-graph",
                    )
                if current is None:
                    return self._attention(
                        journal,
                        advancement="unverified",
                        next_public_read="read.current-graph",
                    )
                if current != {
                    "authored_graph_id": _text(plan, "base_graph_id"),
                    "realized_projection_id": _text(
                        plan, "base_realized_projection_id"
                    ),
                }:
                    return self._attention(
                        journal,
                        execution="succeeded",
                        advancement="unverified",
                        next_public_read="read.current-graph",
                    )
                advanced = self._mutate(
                    journal,
                    route_id="command.graph.advance-current",
                    path_parameters={
                        "workspace_id": self.profile.workspace_id,
                        "run_id": run_id,
                    },
                    body={
                        "plan_id": plan_id,
                        "claim_generation": generation,
                        "expected_current_graph_id": _text(current, "authored_graph_id"),
                        "expected_current_realized_projection_id": _text(
                            current, "realized_projection_id"
                        ),
                        "desired_graph_id": _text(plan, "desired_graph_id"),
                        "desired_realized_projection_id": _text(
                            plan, "desired_realized_projection_id"
                        ),
                        "expected_desired_graph_revision": _integer(
                            plan, "desired_graph_revision", minimum=0
                        ),
                        "idempotency_key": self._new_key(),
                    },
                    credential_role="worker",
                )
                if isinstance(advanced, ClientResult):
                    return advanced
            try:
                observed = self._read(
                    "read.current-graph",
                    path_parameters={"workspace_id": self.profile.workspace_id},
                )
            except ClientAuthorizationError:
                raise
            except (ClientInputError, ClientTransportError):
                return self._attention(
                    journal,
                    execution="succeeded",
                    advancement="unverified",
                    next_public_read="read.current-graph",
                )
            if (
                observed.get("graph_id") != plan.get("desired_graph_id")
                or observed.get("realized_projection_id")
                != plan.get("desired_realized_projection_id")
            ):
                return self._attention(
                    journal,
                    advancement="unverified",
                    next_public_read="read.current-graph",
                )
            journal["phase"] = "converged"
            result = self._status_from_journal(journal)
            journal["last_result"] = result.descriptor()
            self.journal.write(operation_ref, journal)
            return result

    def status(self, operation_ref: str) -> ClientResult:
        journal = self._load(canonical_operation_ref(operation_ref))
        return self._public_status(journal)

    def _finish_prepare(
        self, journal: dict[str, object], prepared: Mapping[str, object]
    ) -> ClientResult:
        status = _text(prepared, "status")
        if status not in {"no-changes", "review-blocked", "approval-required"}:
            return self._attention(journal, next_public_read="read.workspace")
        plan_id = _text(prepared, "plan_id")
        coordinates = _coordinates(journal)
        coordinates["plan_id"] = plan_id
        if "approval_request_id" in prepared:
            coordinates["approval_request_id"] = _text(prepared, "approval_request_id")
        try:
            plan = self._plan_detail(plan_id)
            self._validate_plan(journal, plan)
            changes = _plan_changes(plan)
        except ClientAuthorizationError:
            raise
        except (ClientInputError, ClientTransportError):
            return self._attention(
                journal,
                execution="unverified",
                next_public_read="read.plan-detail",
            )
        _record_plan_coordinates(coordinates, plan)
        approval = None
        if "approval_request_id" in coordinates:
            try:
                approval = self._approval_detail(
                    _coordinate(coordinates, "approval_request_id")
                )
                self._validate_approval(
                    plan,
                    _coordinate(coordinates, "approval_request_id"),
                    approval,
                )
            except ClientAuthorizationError:
                raise
            except (ClientInputError, ClientTransportError):
                return self._attention(
                    journal,
                    execution="unverified",
                    next_public_read="read.approval-detail",
                )
        journal["phase"] = (
            "no-changes"
            if status == "no-changes"
            else "attention-required"
            if status == "review-blocked"
            else "prepared"
        )
        result = _plan_result(journal, plan, approval, status, changes)
        journal["last_result"] = result.descriptor()
        self.journal.write(_text(journal, "operation_ref"), journal)
        return result

    def _mutate(
        self,
        journal: dict[str, object],
        *,
        route_id: str,
        path_parameters: Mapping[str, str],
        body: Mapping[str, object],
        credential_role: str,
        desired_source: Mapping[str, object] | None = None,
    ) -> Mapping[str, object] | ClientResult:
        history = journal["request_history"]
        if not isinstance(history, list) or len(history) >= MAXIMUM_REQUEST_RECORDS:
            return self._attention(journal, next_public_read=_next_read(journal))
        material = dict(body)
        body_digest = _canonical_digest(material)
        retained_body = dict(material)
        if route_id == "command.deployment.prepare":
            retained_body.pop("desired_graph", None)
            if desired_source is None:
                raise JournalError("prepare source reference is missing")
        pending = {
            "route_id": route_id,
            "path_parameters": dict(path_parameters),
            "credential_role": credential_role,
            "idempotency_key": _text(material, "idempotency_key"),
            "body": retained_body,
            "body_sha256": body_digest,
            "desired_source": dict(desired_source) if desired_source is not None else None,
        }
        journal["pending_request"] = pending
        self.journal.write(_text(journal, "operation_ref"), journal)
        return self._dispatch_pending(journal, material)

    def _replay_pending(self, journal: dict[str, object]) -> Mapping[str, object] | ClientResult:
        pending = journal["pending_request"]
        if not isinstance(pending, dict):
            raise JournalError("operation has no pending request")
        body = dict(_mapping(pending, "body"))
        if pending.get("route_id") == "command.deployment.prepare":
            source = _mapping(pending, "desired_source")
            verified_source, desired = _read_desired(Path(_text(source, "path")))
            if verified_source != source:
                return self._attention(
                    journal,
                    execution="unverified",
                    next_public_read="read.workspace",
                )
            body["desired_graph"] = desired
        if _canonical_digest(body) != pending.get("body_sha256"):
            return self._attention(
                journal,
                execution="unverified",
                next_public_read=_next_read(journal),
            )
        return self._dispatch_pending(journal, body)

    def _dispatch_pending(
        self, journal: dict[str, object], body: Mapping[str, object]
    ) -> Mapping[str, object] | ClientResult:
        pending = _mapping(journal, "pending_request")
        try:
            response = self.transport.call(
                _text(pending, "route_id"),
                path_parameters={
                    key: _text_coordinate(value)
                    for key, value in _mapping(pending, "path_parameters").items()
                },
                payload=body,
                credential_role=_text(pending, "credential_role"),
            )
        except ClientAuthorizationError:
            raise
        except ClientTransportError:
            return self._attention(
                journal,
                execution=(
                    "unverified"
                    if _text(pending, "route_id")
                    in {"command.run.start", "command.deployment.execute"}
                    else "not-started"
                ),
                advancement=(
                    "unverified"
                    if _text(pending, "route_id") == "command.graph.advance-current"
                    else "not-attempted"
                ),
                next_public_read=_next_read(journal),
                persist=False,
            )
        route_id = _text(pending, "route_id")
        if not _response_is_bound(
            route_id,
            response,
            pending=pending,
            body=body,
            coordinates=_coordinates(journal),
            workspace_id=self.profile.workspace_id,
        ):
            return self._attention(
                journal,
                execution=(
                    "unverified"
                    if route_id in {"command.run.start", "command.deployment.execute"}
                    else "not-started"
                ),
                advancement=(
                    "unverified"
                    if route_id == "command.graph.advance-current"
                    else "not-attempted"
                ),
                next_public_read=_next_read(journal),
                persist=False,
            )
        projection = _response_coordinates(route_id, response)
        history = journal["request_history"]
        if not isinstance(history, list) or len(history) >= MAXIMUM_REQUEST_RECORDS:
            return self._attention(journal, next_public_read=_next_read(journal), persist=False)
        history.append(
            {
                "route_id": route_id,
                "idempotency_key": _text(pending, "idempotency_key"),
                "body_sha256": _text(pending, "body_sha256"),
                "response": projection,
            }
        )
        _coordinates(journal).update(projection)
        journal["pending_request"] = None
        journal["phase"] = _phase_after(route_id, response)
        self.journal.write(_text(journal, "operation_ref"), journal)
        return response

    def _attention(
        self,
        journal: dict[str, object],
        *,
        execution: str = "not-started",
        advancement: str = "not-attempted",
        next_public_read: str,
        persist: bool = True,
    ) -> ClientResult:
        result = self._status_from_journal(
            journal,
            attention=True,
            execution=execution,
            advancement=advancement,
            next_public_read=next_public_read,
        )
        journal["last_result"] = result.descriptor()
        if persist:
            self.journal.write(_text(journal, "operation_ref"), journal)
        return result

    def _status_from_journal(
        self,
        journal: Mapping[str, object],
        *,
        attention: bool = False,
        execution: str | None = None,
        advancement: str | None = None,
        next_public_read: str | None = None,
        changes: tuple[Mapping[str, object], ...] = (),
        approval: Mapping[str, object] | None = None,
    ) -> ClientResult:
        coordinates = _coordinates(journal)
        phase = _text(journal, "phase")
        if attention:
            status = "attention-required"
        elif phase == "no-changes":
            status = "no-changes"
        elif phase == "converged":
            status = "converged"
        elif phase == "attention-required":
            status = "attention-required"
        elif phase in {"claimed", "started", "executing", "executed", "advanced"}:
            status = "running"
        else:
            status = "planned"
        if execution is None:
            execution = (
                "succeeded"
                if phase in {"executed", "advanced", "converged"}
                else "running"
                if phase in {"claimed", "started", "executing"}
                else "not-started"
            )
        if advancement is None:
            advancement = (
                "advanced"
                if phase in {"advanced", "converged"}
                else "unchanged"
                if phase == "no-changes"
                else "not-attempted"
            )
        required_scope = (
            _text(approval, "required_scope") if approval is not None else None
        )
        destructive = _boolean(approval, "destructive") if approval is not None else None
        return ClientResult(
            status=status,
            operation_ref=_text(journal, "operation_ref"),
            workspace_id=self.profile.workspace_id,
            plan_id=(
                coordinates.get("plan_id")
                if isinstance(coordinates.get("plan_id"), str)
                else None
            ),
            approval_request_id=(
                coordinates.get("approval_request_id")
                if isinstance(coordinates.get("approval_request_id"), str)
                else None
            ),
            run_id=(
                coordinates.get("run_id")
                if isinstance(coordinates.get("run_id"), str)
                else None
            ),
            execution=execution,
            advancement=advancement,
            required_scope=required_scope,
            destructive=destructive,
            changes=changes,
            next_command=("cpk apply" if status == "planned" else None),
            next_public_read=next_public_read,
        )

    def _load(self, operation_ref: str) -> dict[str, object]:
        journal = self.journal.read(operation_ref)
        target = _mapping(journal, "target")
        if (
            target.get("endpoint_sha256") != self.profile.target_digest
            or target.get("workspace_id") != self.profile.workspace_id
        ):
            raise JournalError("operation target does not match the selected profile")
        return journal

    def _public_status(self, journal: Mapping[str, object]) -> ClientResult:
        coordinates = _coordinates(journal)
        pending = journal.get("pending_request")
        execution = None
        advancement = None
        approval_problem = False
        next_read = _next_read(journal)
        changes: tuple[Mapping[str, object], ...] = ()
        plan = None
        approval = None
        try:
            workspace = self._workspace()
            current = _pointer(workspace, "current")
            if "plan_id" in coordinates:
                plan = self._plan_detail(_coordinate(coordinates, "plan_id"))
                self._validate_plan(journal, plan)
                changes = _plan_changes(plan)
            if "approval_request_id" in coordinates:
                if plan is None:
                    raise ClientInputError("public plan coordinates are invalid")
                approval = self._approval_detail(
                    _coordinate(coordinates, "approval_request_id")
                )
                self._validate_approval(
                    plan,
                    _coordinate(coordinates, "approval_request_id"),
                    approval,
                )
                approval_problem = approval.get("state") not in {"pending", "approved"}
            run_id = coordinates.get("run_id")
            if isinstance(run_id, str):
                items = self._page(
                    "read.plan-runs",
                    path_parameters={
                        "workspace_id": self.profile.workspace_id,
                        "plan_id": _coordinate(coordinates, "plan_id"),
                    },
                )
                matching = [
                    item
                    for item in items
                    if isinstance(item, dict) and item.get("run_id") == run_id
                ]
                if len(matching) != 1:
                    return self._status_from_journal(
                        journal,
                        attention=True,
                        execution="unverified",
                        advancement="unverified",
                        next_public_read="read.plan-runs",
                    )
                run_status = matching[0].get("status")
                execution = (
                    "succeeded"
                    if run_status == "succeeded"
                    else "failed"
                    if run_status == "failed"
                    else "running"
                    if run_status in {"queued", "claimed", "running"}
                    else "unverified"
                )
                self._page(
                    "read.run-events",
                    path_parameters={"workspace_id": self.profile.workspace_id, "run_id": run_id},
                )
            desired_graph_id = coordinates.get("desired_graph_id")
            desired_projection_id = coordinates.get("desired_realized_projection_id")
            if isinstance(desired_graph_id, str):
                observed = self._read(
                    "read.current-graph",
                    path_parameters={"workspace_id": self.profile.workspace_id},
                )
                current = {
                    "authored_graph_id": _text(observed, "graph_id"),
                    "realized_projection_id": _text(
                        observed, "realized_projection_id"
                    ),
                }
            if (
                current is not None
                and isinstance(desired_graph_id, str)
                and isinstance(desired_projection_id, str)
                and current
                == {
                    "authored_graph_id": desired_graph_id,
                    "realized_projection_id": desired_projection_id,
                }
            ):
                advancement = "advanced"
        except ClientAuthorizationError:
            raise
        except (ClientInputError, ClientTransportError):
            return self._status_from_journal(
                journal,
                attention=True,
                execution="unverified" if pending is not None else execution,
                advancement="unverified" if pending is not None else advancement,
                next_public_read=next_read,
                changes=changes,
                approval=approval,
            )
        if pending is not None:
            route_id = pending.get("route_id") if isinstance(pending, Mapping) else None
            return self._status_from_journal(
                journal,
                attention=True,
                execution=(
                    "unverified"
                    if route_id in {"command.run.start", "command.deployment.execute"}
                    else execution
                ),
                advancement=(
                    "unverified"
                    if route_id == "command.graph.advance-current"
                    else advancement
                ),
                next_public_read=next_read,
                changes=changes,
                approval=approval,
            )
        phase = _text(journal, "phase")
        attention = (
            approval_problem
            or execution in {"failed", "unverified"}
            or (phase in {"advanced", "converged"} and advancement != "advanced")
        )
        return self._status_from_journal(
            journal,
            attention=attention,
            execution=execution,
            advancement=advancement,
            next_public_read=next_read if attention else None,
            changes=changes,
            approval=approval,
        )

    def _workspace(self) -> Mapping[str, object]:
        value = self._read(
            "read.workspace",
            path_parameters={"workspace_id": self.profile.workspace_id},
        )
        return _mapping(value, "workspace")

    def _plan_detail(self, plan_id: str) -> Mapping[str, object]:
        value = self._read(
            "read.plan-detail",
            path_parameters={"workspace_id": self.profile.workspace_id, "plan_id": plan_id},
        )
        return _mapping(value, "plan")

    def _approval_detail(self, approval_id: str) -> Mapping[str, object]:
        value = self._read(
            "read.approval-detail",
            path_parameters={
                "workspace_id": self.profile.workspace_id,
                "approval_id": approval_id,
            },
        )
        return _mapping(value, "approval")

    def _read(
        self,
        route_id: str,
        *,
        path_parameters: Mapping[str, str],
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return self.transport.call(
            route_id,
            path_parameters=path_parameters,
            payload=payload or {},
            credential_role="operator",
        )

    def _page(
        self,
        route_id: str,
        *,
        path_parameters: Mapping[str, str],
    ) -> list[object]:
        items: list[object] = []
        cursor = None
        seen = set()
        for _ in range(MAXIMUM_PUBLIC_PAGES):
            payload: dict[str, object] = {"limit": MAXIMUM_PAGE_ITEMS}
            if cursor is not None:
                payload["after"] = cursor
            page = self._read(
                route_id,
                path_parameters=path_parameters,
                payload=payload,
            )
            batch = page.get("items")
            if not isinstance(batch, list) or len(batch) > MAXIMUM_PAGE_ITEMS:
                raise ClientInputError("public history page is invalid")
            items.extend(batch)
            cursor = page.get("next_cursor")
            if cursor is None:
                return items
            if not isinstance(cursor, dict):
                raise ClientInputError("public history cursor is invalid")
            try:
                cursor_key = json.dumps(
                    cursor,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            except (TypeError, ValueError) as error:
                raise ClientInputError("public history cursor is invalid") from error
            if (
                len(cursor_key.encode("utf-8")) > MAXIMUM_CURSOR_BYTES
                or cursor_key in seen
            ):
                raise ClientInputError("public history cursor is invalid")
            seen.add(cursor_key)
        raise ClientInputError("public history page budget is exhausted")

    def _validate_plan(self, journal: Mapping[str, object], plan: Mapping[str, object]) -> None:
        coordinates = _coordinates(journal)
        for name in (
            "plan_id",
            "session_id",
            "base_graph_id",
            "base_realized_projection_id",
            "desired_graph_id",
            "desired_realized_projection_id",
            "desired_graph_revision",
        ):
            if name in coordinates and plan.get(name) != coordinates[name]:
                raise ClientInputError("prepared plan coordinates are stale")

    def _validate_approval(
        self,
        plan: Mapping[str, object],
        approval_id: str,
        approval: Mapping[str, object],
    ) -> None:
        scope = approval.get("required_scope")
        destructive = approval.get("destructive")
        if (
            approval.get("request_id") != approval_id
            or approval.get("session_id") != plan.get("session_id")
            or scope not in {"plan:approve", "plan:approve-destructive"}
            or type(destructive) is not bool
            or destructive != (scope == "plan:approve-destructive")
        ):
            raise ClientInputError("prepared approval coordinates are stale")

    def _new_key(self) -> str:
        return canonical_operation_ref(self._identity_factory())


def _new_journal(
    profile: ClientProfile,
    operation_ref: str,
    desired: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema": JOURNAL_SCHEMA,
        "operation_ref": operation_ref,
        "target": {
            "endpoint_sha256": profile.target_digest,
            "workspace_id": profile.workspace_id,
        },
        "desired": dict(desired),
        "phase": "planning",
        "pending_request": None,
        "coordinates": {},
        "request_history": [],
        "last_result": None,
    }


def _read_desired(path: Path) -> tuple[dict[str, object], dict[str, object]]:
    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as error:
        raise ClientInputError("desired graph file is unavailable") from error
    try:
        information = os.fstat(descriptor)
        if not stat.S_ISREG(information.st_mode) or information.st_size > MAXIMUM_DESIRED_BYTES:
            raise ClientInputError("desired graph file is invalid")
        chunks = []
        remaining = MAXIMUM_DESIRED_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(raw) > MAXIMUM_DESIRED_BYTES:
        raise ClientInputError("desired graph exceeds the public request bound")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise ClientInputError("desired graph document is invalid") from error
    if not isinstance(value, dict):
        raise ClientInputError("desired graph document must be an object")
    return (
        {"path": str(absolute), "size": len(raw), "sha256": sha256(raw).hexdigest()},
        value,
    )


def _plan_result(
    journal: Mapping[str, object],
    plan: Mapping[str, object],
    approval: Mapping[str, object] | None,
    preparation_status: str,
    changes: tuple[Mapping[str, object], ...],
) -> ClientResult:
    required_scope = None
    destructive = None
    if approval is not None:
        required_scope = _text(approval, "required_scope")
        destructive = _boolean(approval, "destructive")
    return ClientResult(
        status=(
            "no-changes"
            if preparation_status == "no-changes"
            else "attention-required"
            if preparation_status == "review-blocked"
            else "planned"
        ),
        operation_ref=_text(journal, "operation_ref"),
        workspace_id=_text(_mapping(journal, "target"), "workspace_id"),
        plan_id=_text(plan, "plan_id"),
        approval_request_id=(
            _text(approval, "request_id") if approval is not None else None
        ),
        required_scope=required_scope,
        destructive=destructive,
        changes=changes,
        advancement="unchanged" if preparation_status == "no-changes" else "not-attempted",
        next_command=("cpk apply" if preparation_status == "approval-required" else None),
        next_public_read="read.plan-detail",
    )


def _plan_changes(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    payload = _mapping(plan, "payload")
    raw_activities = payload.get("activities", [])
    if not isinstance(raw_activities, list):
        raise ClientInputError("public plan activities are invalid")
    changes = []
    for activity in raw_activities:
        if not isinstance(activity, dict):
            raise ClientInputError("public plan activities are invalid")
        operation = _mapping(activity, "operation")
        target = _mapping(operation, "target")
        projected_target = {
            key: _text_coordinate(value)
            for key, value in target.items()
            if key in {"kind", "node_id", "runtime_id", "edge_id"}
        }
        if "kind" not in projected_target:
            raise ClientInputError("public plan activity target is invalid")
        changes.append(
            {
                "activity_id": _text(activity, "activity_id"),
                "operation": _text(operation, "kind"),
                "target": projected_target,
            }
        )
    return tuple(changes)


def _response_coordinates(route_id: str, response: Mapping[str, object]) -> dict[str, object]:
    if route_id == "command.deployment.prepare":
        result: dict[str, object] = {"plan_id": _text(response, "plan_id")}
        if "approval_request_id" in response:
            result["approval_request_id"] = _text(response, "approval_request_id")
        return result
    if route_id == "command.approval.decide":
        return {"approval_state": _text(response, "state")}
    if route_id == "command.deployment.admit":
        return {"execution_request_id": _text(response, "execution_request_id")}
    if route_id == "command.run.claim":
        return {
            "run_id": _text(response, "run_id"),
            "claim_generation": _integer(response, "claim_generation", minimum=1),
        }
    if route_id == "command.run.start":
        return {"run_status": _text(response, "run_status")}
    if route_id == "command.deployment.execute":
        return {
            "run_id": _text(response, "run_id"),
            "run_status": _text(response, "run_status"),
            "coordinator_status": _text(response, "coordinator_status"),
            "effects_attempted": _integer(response, "effects_attempted", minimum=0),
            **(
                {"activity_id": _text(response, "activity_id")}
                if response.get("activity_id") is not None
                else {}
            ),
        }
    if route_id == "command.graph.advance-current":
        return {
            "advanced_graph_id": _text(response, "to_graph_id"),
            "advanced_projection_id": _text(response, "to_realized_projection_id"),
            "advanced_revision": _integer(response, "desired_graph_revision", minimum=0),
        }
    raise ClientInputError("public mutation route is unsupported")


def _phase_after(route_id: str, response: Mapping[str, object]) -> str:
    if route_id == "command.deployment.prepare":
        return "prepared"
    if route_id == "command.approval.decide":
        return "approved"
    if route_id == "command.deployment.admit":
        return "admitted"
    if route_id == "command.run.claim":
        return "claimed"
    if route_id == "command.run.start":
        return "started"
    if route_id == "command.deployment.execute":
        status = response.get("coordinator_status")
        if status == "completed":
            return "executed"
        if status == "progressed":
            return "executing"
        return "attention-required"
    if route_id == "command.graph.advance-current":
        return "advanced"
    raise ClientInputError("public mutation route is unsupported")


def _response_is_bound(
    route_id: str,
    response: Mapping[str, object],
    *,
    pending: Mapping[str, object],
    body: Mapping[str, object],
    coordinates: Mapping[str, object],
    workspace_id: str,
) -> bool:
    path = pending.get("path_parameters")
    if not isinstance(path, Mapping):
        return False
    if route_id == "command.deployment.prepare":
        return response.get("workspace_id") == workspace_id
    if route_id == "command.approval.decide":
        return (
            response.get("request_id") == path.get("approval_id")
            and response.get("state") == "approved"
        )
    if route_id == "command.deployment.admit":
        return _is_text_coordinate(response.get("execution_request_id"))
    if route_id == "command.run.claim":
        return (
            response.get("execution_request_id") == path.get("run_id")
            and _is_text_coordinate(response.get("run_id"))
            and response.get("run_status") == "claimed"
            and _is_positive_integer(response.get("claim_generation"))
        )
    if route_id == "command.run.start":
        return (
            response.get("execution_request_id")
            == coordinates.get("execution_request_id")
            and response.get("run_id") == path.get("run_id")
            and response.get("run_status") == "running"
            and response.get("claim_generation") == body.get("claim_generation")
        )
    if route_id == "command.deployment.execute":
        status = response.get("coordinator_status")
        run_status = response.get("run_status")
        activity = response.get("activity_id")
        effects = response.get("effects_attempted")
        return (
            response.get("run_id") == path.get("run_id")
            and type(effects) is int
            and 0 <= effects <= body.get("max_effects", -1)
            and (
                status == "completed"
                and run_status == "succeeded"
                and activity is None
                or status in {"progressed", "in-flight"}
                and run_status == "running"
                and _is_text_coordinate(activity)
                or status == "failed"
                and run_status == "failed"
                or status == "unsupported"
                and run_status == "failed"
                and effects == 1
                and _is_text_coordinate(activity)
                or status in {"uncertain", "blocked"}
                and run_status in {"running", "failed"}
            )
        )
    if route_id == "command.graph.advance-current":
        return (
            response.get("from_graph_id") == body.get("expected_current_graph_id")
            and response.get("from_realized_projection_id")
            == body.get("expected_current_realized_projection_id")
            and response.get("to_graph_id") == body.get("desired_graph_id")
            and response.get("to_realized_projection_id")
            == body.get("desired_realized_projection_id")
            and response.get("desired_graph_revision")
            == body.get("expected_desired_graph_revision")
        )
    return False


def _is_text_coordinate(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        return False
    return 0 < size <= 512


def _is_positive_integer(value: object) -> bool:
    return type(value) is int and value > 0


def _record_plan_coordinates(
    coordinates: dict[str, object], plan: Mapping[str, object]
) -> None:
    for name in (
        "plan_id",
        "session_id",
        "base_graph_id",
        "base_realized_projection_id",
        "desired_graph_id",
        "desired_realized_projection_id",
    ):
        coordinates[name] = _text(plan, name)
    coordinates["desired_graph_revision"] = _integer(
        plan, "desired_graph_revision", minimum=0
    )


def _pointer(workspace: Mapping[str, object], prefix: str) -> dict[str, str] | None:
    graph = workspace.get(f"{prefix}_graph_id")
    projection = workspace.get(f"{prefix}_realized_projection_id")
    if graph is None:
        if projection is not None:
            raise ClientInputError("workspace graph pointer is invalid")
        return None
    return {
        "authored_graph_id": _text_coordinate(graph),
        "realized_projection_id": _text_coordinate(projection),
    }


def _next_read(journal: Mapping[str, object]) -> str:
    coordinates = _coordinates(journal)
    if "run_id" in coordinates:
        return "read.run-events"
    if "plan_id" in coordinates:
        return "read.plan-detail"
    return "read.workspace"


def _coordinates(journal: Mapping[str, object]) -> dict[str, object]:
    value = journal.get("coordinates")
    if not isinstance(value, dict):
        raise JournalError("operation journal coordinates are invalid")
    return value


def _mapping(value: Mapping[str, object], name: str) -> Mapping[str, object]:
    item = value.get(name)
    if not isinstance(item, Mapping):
        raise ClientInputError(f"public {name} is invalid")
    return item


def _text(value: Mapping[str, object], name: str) -> str:
    return _text_coordinate(value.get(name))


def _text_coordinate(value: object) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 512:
        raise ClientInputError("public coordinate is invalid")
    return value


def _coordinate(value: Mapping[str, object], name: str) -> str:
    return _text_coordinate(value.get(name))


def _integer(value: Mapping[str, object], name: str, *, minimum: int) -> int:
    item = value.get(name)
    if type(item) is not int or item < minimum:
        raise ClientInputError(f"public {name} is invalid")
    return item


def _boolean(value: Mapping[str, object], name: str) -> bool:
    item = value.get(name)
    if type(item) is not bool:
        raise ClientInputError(f"public {name} is invalid")
    return item


def _bounded_text(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise ClientInputError(f"{name} is invalid")
    return value


def _canonical_digest(value: Mapping[str, object]) -> str:
    try:
        raw = json.dumps(
            dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ClientInputError("public request is invalid") from error
    if len(raw) > MAXIMUM_DESIRED_BYTES:
        raise ClientInputError("public request exceeds its contract")
    return sha256(raw).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON member")
        value[key] = item
    return value
