"""Bounded private locator journal for one public client invocation."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
from typing import Iterator, Mapping
from uuid import UUID


JOURNAL_SCHEMA = "cpk.client-invocation.v1"
MAXIMUM_JOURNAL_BYTES = 1_048_576
MAXIMUM_REQUEST_RECORDS = 128
_JOURNAL_KEYS = {
    "schema",
    "operation_ref",
    "target",
    "desired",
    "phase",
    "pending_request",
    "coordinates",
    "request_history",
    "last_result",
}
_PHASES = frozenset(
    {
        "planning",
        "prepared",
        "no-changes",
        "approved",
        "admitted",
        "claimed",
        "started",
        "executing",
        "executed",
        "advanced",
        "converged",
        "attention-required",
    }
)
_PLAN_COORDINATES = frozenset(
    {
        "plan_id",
        "session_id",
        "base_graph_id",
        "base_realized_projection_id",
        "desired_graph_id",
        "desired_realized_projection_id",
        "desired_graph_revision",
    }
)
_COORDINATE_KEYS = _PLAN_COORDINATES | {
    "approval_request_id",
    "approval_state",
    "execution_request_id",
    "run_id",
    "claim_generation",
    "run_status",
    "coordinator_status",
    "effects_attempted",
    "activity_id",
    "advanced_graph_id",
    "advanced_projection_id",
    "advanced_revision",
}
_INTEGER_COORDINATES = {
    "desired_graph_revision",
    "claim_generation",
    "effects_attempted",
    "advanced_revision",
}
_MUTATION_ROLES = {
    "command.deployment.prepare": "operator",
    "command.approval.decide": "approver",
    "command.deployment.admit": "operator",
    "command.run.claim": "worker",
    "command.run.start": "worker",
    "command.deployment.execute": "worker",
    "command.graph.advance-current": "worker",
}
_PENDING_PHASES = {
    "command.deployment.prepare": {"planning"},
    "command.approval.decide": {"prepared"},
    "command.deployment.admit": {"prepared", "approved"},
    "command.run.claim": {"admitted"},
    "command.run.start": {"claimed"},
    "command.deployment.execute": {"started", "executing"},
    "command.graph.advance-current": {"executed"},
}


class JournalError(RuntimeError):
    """Fixed private-state failure."""


def canonical_operation_ref(value: object) -> str:
    if not isinstance(value, str):
        raise JournalError("operation reference is invalid")
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise JournalError("operation reference is invalid") from error
    if str(parsed) != value or parsed.version != 4:
        raise JournalError("operation reference is invalid")
    return value


class JournalStore:
    def __init__(self, state_directory: Path) -> None:
        if not isinstance(state_directory, Path) or not state_directory.is_absolute():
            raise JournalError("state directory is invalid")
        self.root = state_directory / "invocations"

    def initialize(self) -> None:
        _reject_symlink_components(self.root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _reject_symlink_components(self.root)
        information = os.lstat(self.root)
        if (
            not stat.S_ISDIR(information.st_mode)
            or stat.S_ISLNK(information.st_mode)
            or information.st_uid != os.getuid()
            or stat.S_IMODE(information.st_mode) & 0o077
        ):
            raise JournalError("state directory is unsafe")

    @contextmanager
    def mutation_lock(self, operation_ref: str) -> Iterator[None]:
        operation_ref = canonical_operation_ref(operation_ref)
        self.initialize()
        path = self.root / f"{operation_ref}.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags, 0o600)
        except OSError as error:
            raise JournalError("operation lock is unavailable") from error
        try:
            information = os.fstat(descriptor)
            if (
                not stat.S_ISREG(information.st_mode)
                or information.st_uid != os.getuid()
                or stat.S_IMODE(information.st_mode) != 0o600
            ):
                raise JournalError("operation lock is unsafe")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise JournalError("operation is already being changed") from error
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def read(self, operation_ref: str) -> dict[str, object]:
        operation_ref = canonical_operation_ref(operation_ref)
        self.initialize()
        path = self.root / f"{operation_ref}.json"
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise JournalError("operation journal is unavailable") from error
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_size > MAXIMUM_JOURNAL_BYTES
            ):
                raise JournalError("operation journal is unsafe")
            chunks = []
            remaining = MAXIMUM_JOURNAL_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(descriptor)
            if (
                len(raw) > MAXIMUM_JOURNAL_BYTES
                or before.st_ino != after.st_ino
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                raise JournalError("operation journal changed during read")
        finally:
            os.close(descriptor)
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise JournalError("operation journal is invalid") from error
        _validate_journal(value, operation_ref)
        return value

    def create(self, operation_ref: str, value: Mapping[str, object]) -> None:
        """Publish a new invocation without replacing any pre-existing path."""

        operation_ref = canonical_operation_ref(operation_ref)
        self.initialize()
        raw = _encode_journal(operation_ref, value)
        path = self.root / f"{operation_ref}.json"
        partial = self.root / f"{operation_ref}.json.part"
        descriptor, owned_identity = _write_owned_partial(partial, raw)
        try:
            os.close(descriptor)
            descriptor = -1
            try:
                os.link(partial, path, follow_symlinks=False)
            except FileExistsError as error:
                raise JournalError("operation reference already exists") from error
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as error:
            raise JournalError("operation journal could not be persisted") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            _unlink_owned_partial(partial, owned_identity)

    def write(self, operation_ref: str, value: Mapping[str, object]) -> None:
        operation_ref = canonical_operation_ref(operation_ref)
        self.initialize()
        raw = _encode_journal(operation_ref, value)
        path = self.root / f"{operation_ref}.json"
        partial = self.root / f"{operation_ref}.json.part"
        existing_identity = _validated_journal_identity(path)
        descriptor, owned_identity = _write_owned_partial(partial, raw)
        try:
            os.close(descriptor)
            descriptor = -1
            current = os.lstat(path)
            if (
                current.st_dev,
                current.st_ino,
            ) != existing_identity or not stat.S_ISREG(current.st_mode):
                raise JournalError("operation journal changed before replacement")
            os.replace(partial, path)
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as error:
            raise JournalError("operation journal could not be persisted") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            _unlink_owned_partial(partial, owned_identity)


def _validate_journal(value: object, operation_ref: str) -> None:
    if not isinstance(value, dict) or set(value) != _JOURNAL_KEYS:
        raise JournalError("operation journal is invalid")
    if value["schema"] != JOURNAL_SCHEMA or value["operation_ref"] != operation_ref:
        raise JournalError("operation journal identity is invalid")
    target = value["target"]
    if not isinstance(target, dict) or set(target) != {"endpoint_sha256", "workspace_id"}:
        raise JournalError("operation journal target is invalid")
    if (
        not _is_sha256(target["endpoint_sha256"])
        or not _is_text(target["workspace_id"])
    ):
        raise JournalError("operation journal target is invalid")
    desired = value["desired"]
    if (
        not isinstance(desired, dict)
        or set(desired) != {"path", "size", "sha256"}
        or not isinstance(desired["path"], str)
        or not Path(desired["path"]).is_absolute()
        or type(desired["size"]) is not int
        or not 0 <= desired["size"] <= 65_536
        or not _is_sha256(desired["sha256"])
    ):
        raise JournalError("operation journal desired reference is invalid")
    phase = value["phase"]
    if phase not in _PHASES:
        raise JournalError("operation journal phase is invalid")
    coordinates = value["coordinates"]
    if not isinstance(coordinates, dict) or not set(coordinates) <= _COORDINATE_KEYS:
        raise JournalError("operation journal coordinates are invalid")
    for name, item in coordinates.items():
        if name in _INTEGER_COORDINATES:
            if type(item) is not int or item < 0:
                raise JournalError("operation journal coordinates are invalid")
        elif not _is_text(item):
            raise JournalError("operation journal coordinates are invalid")
    if phase == "planning" and coordinates:
        raise JournalError("operation journal phase coordinates are invalid")
    if phase not in {"planning", "attention-required"} and "plan_id" not in coordinates:
        raise JournalError("operation journal phase coordinates are invalid")
    if phase in {
        "no-changes",
        "approved",
        "admitted",
        "claimed",
        "started",
        "executing",
        "executed",
        "advanced",
        "converged",
    } and not _PLAN_COORDINATES <= set(coordinates):
        raise JournalError("operation journal phase coordinates are invalid")
    required_by_phase = {
        "approved": {"approval_request_id", "approval_state"},
        "admitted": {"execution_request_id"},
        "claimed": {"execution_request_id", "run_id", "claim_generation"},
        "started": {
            "execution_request_id",
            "run_id",
            "claim_generation",
            "run_status",
        },
        "executing": {
            "execution_request_id",
            "run_id",
            "claim_generation",
            "run_status",
            "coordinator_status",
            "effects_attempted",
        },
        "executed": {
            "execution_request_id",
            "run_id",
            "claim_generation",
            "run_status",
            "coordinator_status",
            "effects_attempted",
        },
        "advanced": {
            "execution_request_id",
            "run_id",
            "claim_generation",
            "run_status",
            "coordinator_status",
            "effects_attempted",
            "advanced_graph_id",
            "advanced_projection_id",
            "advanced_revision",
        },
        "converged": {
            "execution_request_id",
            "run_id",
            "claim_generation",
            "run_status",
            "coordinator_status",
            "effects_attempted",
            "advanced_graph_id",
            "advanced_projection_id",
            "advanced_revision",
        },
    }
    if not required_by_phase.get(phase, set()) <= set(coordinates):
        raise JournalError("operation journal phase coordinates are invalid")
    if phase in {"executed", "advanced", "converged"} and (
        coordinates.get("run_status") != "succeeded"
        or coordinates.get("coordinator_status") != "completed"
    ):
        raise JournalError("operation journal terminal coordinates are invalid")
    if phase == "started" and coordinates.get("run_status") != "running":
        raise JournalError("operation journal run coordinates are invalid")
    if phase == "executing" and (
        coordinates.get("run_status") != "running"
        or coordinates.get("coordinator_status") != "progressed"
    ):
        raise JournalError("operation journal run coordinates are invalid")
    if phase in {"advanced", "converged"} and (
        coordinates.get("advanced_graph_id") != coordinates.get("desired_graph_id")
        or coordinates.get("advanced_projection_id")
        != coordinates.get("desired_realized_projection_id")
        or coordinates.get("advanced_revision")
        != coordinates.get("desired_graph_revision")
    ):
        raise JournalError("operation journal advancement coordinates are invalid")
    pending = value["pending_request"]
    if pending is not None:
        _validate_pending(pending, phase, target, desired, coordinates)
    history = value["request_history"]
    if not isinstance(history, list) or len(history) > MAXIMUM_REQUEST_RECORDS:
        raise JournalError("operation journal request budget is exhausted")
    for record in history:
        if (
            not isinstance(record, dict)
            or set(record)
            != {"route_id", "idempotency_key", "body_sha256", "response"}
            or record["route_id"] not in _MUTATION_ROLES
            or not _is_uuid4(record["idempotency_key"])
            or not _is_sha256(record["body_sha256"])
            or not isinstance(record["response"], dict)
        ):
            raise JournalError("operation journal request history is invalid")
    if value["last_result"] is not None:
        _validate_result(value["last_result"], operation_ref, target, coordinates)


def _validate_pending(
    pending: object,
    phase: str,
    target: Mapping[str, object],
    desired: Mapping[str, object],
    coordinates: Mapping[str, object],
) -> None:
    keys = {
        "route_id",
        "path_parameters",
        "credential_role",
        "idempotency_key",
        "body",
        "body_sha256",
        "desired_source",
    }
    if not isinstance(pending, dict) or set(pending) != keys:
        raise JournalError("operation journal pending request is invalid")
    route_id = pending["route_id"]
    if (
        route_id not in _MUTATION_ROLES
        or pending["credential_role"] != _MUTATION_ROLES[route_id]
        or phase not in _PENDING_PHASES[route_id]
        or not _is_uuid4(pending["idempotency_key"])
        or not _is_sha256(pending["body_sha256"])
    ):
        raise JournalError("operation journal pending request is invalid")
    path = pending["path_parameters"]
    body = pending["body"]
    if not isinstance(path, dict) or not isinstance(body, dict):
        raise JournalError("operation journal pending request is invalid")
    if body.get("idempotency_key") != pending["idempotency_key"]:
        raise JournalError("operation journal pending request is invalid")
    body_keys = {
        "command.deployment.prepare": {
            "expected_current",
            "expected_desired",
            "expected_desired_graph_revision",
            "title",
            "idempotency_key",
        },
        "command.approval.decide": {
            "session_id",
            "decision",
            "idempotency_key",
        },
        "command.deployment.admit": {
            "session_id",
            "approval_request_id",
            "readiness",
            "idempotency_key",
        },
        "command.run.claim": {"lease_duration_seconds", "idempotency_key"},
        "command.run.start": {"claim_generation", "idempotency_key"},
        "command.deployment.execute": {
            "claim_generation",
            "max_effects",
            "idempotency_key",
        },
        "command.graph.advance-current": {
            "plan_id",
            "claim_generation",
            "expected_current_graph_id",
            "expected_current_realized_projection_id",
            "desired_graph_id",
            "desired_realized_projection_id",
            "expected_desired_graph_revision",
            "idempotency_key",
        },
    }
    path_keys = {
        "command.deployment.prepare": {"workspace_id"},
        "command.approval.decide": {"workspace_id", "approval_id"},
        "command.deployment.admit": {"workspace_id", "plan_id"},
        "command.run.claim": {"workspace_id", "run_id"},
        "command.run.start": {"workspace_id", "run_id"},
        "command.deployment.execute": {"workspace_id", "run_id"},
        "command.graph.advance-current": {"workspace_id", "run_id"},
    }
    if set(body) != body_keys[route_id] or set(path) != path_keys[route_id]:
        raise JournalError("operation journal pending request is invalid")
    if path.get("workspace_id") != target["workspace_id"]:
        raise JournalError("operation journal pending target is invalid")
    source = pending["desired_source"]
    if route_id == "command.deployment.prepare":
        if (
            source != desired
            or not _valid_pointer(body.get("expected_current"))
            or (
                body.get("expected_desired") is not None
                and not _valid_pointer(body.get("expected_desired"))
            )
            or type(body.get("expected_desired_graph_revision")) is not int
            or body["expected_desired_graph_revision"] < 0
            or not _is_text(body.get("title"))
        ):
            raise JournalError("operation journal prepare request is invalid")
        return
    if source is not None:
        raise JournalError("operation journal pending request is invalid")
    if route_id == "command.approval.decide":
        valid = (
            path.get("approval_id") == coordinates.get("approval_request_id")
            and body.get("session_id") == coordinates.get("session_id")
            and body.get("decision") == "approved"
        )
    elif route_id == "command.deployment.admit":
        valid = (
            path.get("plan_id") == coordinates.get("plan_id")
            and body.get("session_id") == coordinates.get("session_id")
            and body.get("approval_request_id")
            == coordinates.get("approval_request_id")
            and body.get("readiness") == []
        )
    elif route_id == "command.run.claim":
        valid = (
            path.get("run_id") == coordinates.get("execution_request_id")
            and type(body.get("lease_duration_seconds")) is int
            and 1 <= body["lease_duration_seconds"] <= 86_400
        )
    elif route_id in {"command.run.start", "command.deployment.execute"}:
        valid = (
            path.get("run_id") == coordinates.get("run_id")
            and body.get("claim_generation") == coordinates.get("claim_generation")
            and (
                route_id != "command.deployment.execute"
                or body.get("max_effects") == 1
            )
        )
    else:
        valid = (
            path.get("run_id") == coordinates.get("run_id")
            and body.get("plan_id") == coordinates.get("plan_id")
            and body.get("claim_generation") == coordinates.get("claim_generation")
            and body.get("expected_current_graph_id")
            == coordinates.get("base_graph_id")
            and body.get("expected_current_realized_projection_id")
            == coordinates.get("base_realized_projection_id")
            and body.get("desired_graph_id") == coordinates.get("desired_graph_id")
            and body.get("desired_realized_projection_id")
            == coordinates.get("desired_realized_projection_id")
            and body.get("expected_desired_graph_revision")
            == coordinates.get("desired_graph_revision")
        )
    if not valid:
        raise JournalError("operation journal pending coordinates are invalid")


def _validate_result(
    result: object,
    operation_ref: str,
    target: Mapping[str, object],
    coordinates: Mapping[str, object],
) -> None:
    required = {
        "schema",
        "status",
        "operation_ref",
        "workspace_id",
        "execution",
        "advancement",
        "observation",
        "changes",
        "next",
    }
    optional = {
        "plan_id",
        "approval_request_id",
        "run_id",
        "required_scope",
        "destructive",
    }
    if (
        not isinstance(result, dict)
        or not required <= set(result) <= required | optional
        or result["schema"] != "cpk.client-result.v1"
        or result["operation_ref"] != operation_ref
        or result["workspace_id"] != target["workspace_id"]
        or result["status"]
        not in {
            "planned",
            "running",
            "no-changes",
            "converged",
            "attention-required",
        }
        or result["execution"]
        not in {
            "not-started",
            "running",
            "succeeded",
            "blocked",
            "failed",
            "unsupported",
            "uncertain",
            "unverified",
        }
        or result["advancement"]
        not in {"not-attempted", "advanced", "unchanged", "unverified"}
    ):
        raise JournalError("operation journal result is invalid")
    observation = result["observation"]
    if (
        not isinstance(observation, dict)
        or set(observation) != {"health", "freshness"}
        or observation["health"] not in {"healthy", "unhealthy", "unknown"}
        or observation["freshness"] not in {"fresh", "stale", "unknown"}
    ):
        raise JournalError("operation journal result is invalid")
    changes = result["changes"]
    if not isinstance(changes, list) or len(changes) > MAXIMUM_REQUEST_RECORDS:
        raise JournalError("operation journal result is invalid")
    for change in changes:
        if (
            not isinstance(change, dict)
            or set(change) != {"activity_id", "operation", "target"}
            or any(
                not _is_text(change[name])
                for name in ("activity_id", "operation")
            )
            or not _valid_change_target(change["target"])
        ):
            raise JournalError("operation journal result is invalid")
    next_value = result["next"]
    if (
        not isinstance(next_value, dict)
        or not set(next_value) <= {"command", "public_read"}
        or not all(_is_text(item) for item in next_value.values())
    ):
        raise JournalError("operation journal result is invalid")
    for name in ("plan_id", "approval_request_id", "run_id"):
        if name in result and result[name] != coordinates.get(name):
            raise JournalError("operation journal result coordinates are invalid")
    if "required_scope" in result and not _is_text(result["required_scope"]):
        raise JournalError("operation journal result is invalid")
    if "destructive" in result and type(result["destructive"]) is not bool:
        raise JournalError("operation journal result is invalid")


def _valid_pointer(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"authored_graph_id", "realized_projection_id"}
        and all(_is_text(item) for item in value.values())
    )


def _valid_change_target(value: object) -> bool:
    return (
        isinstance(value, dict)
        and "kind" in value
        and set(value) <= {"kind", "node_id", "runtime_id", "edge_id"}
        and all(_is_text(item) for item in value.values())
    )


def _is_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        return False
    return 0 < size <= 512


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_uuid4(value: object) -> bool:
    try:
        return canonical_operation_ref(value) == value
    except JournalError:
        return False


def _encode_journal(operation_ref: str, value: Mapping[str, object]) -> bytes:
    candidate = dict(value)
    _validate_journal(candidate, operation_ref)
    try:
        raw = json.dumps(
            candidate, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise JournalError("operation journal is invalid") from error
    if len(raw) > MAXIMUM_JOURNAL_BYTES:
        raise JournalError("operation journal exceeds its bound")
    return raw


def _write_owned_partial(path: Path, raw: bytes) -> tuple[int, tuple[int, int]]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    identity = None
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise JournalError("journal partial is unavailable") from error
    try:
        information = os.fstat(descriptor)
        identity = (information.st_dev, information.st_ino)
        if not stat.S_ISREG(information.st_mode) or stat.S_IMODE(information.st_mode) != 0o600:
            raise JournalError("journal partial is unsafe")
        written = 0
        while written < len(raw):
            count = os.write(descriptor, raw[written:])
            if count <= 0:
                raise OSError("journal write made no progress")
            written += count
        os.fsync(descriptor)
        return descriptor, identity
    except BaseException:
        os.close(descriptor)
        _unlink_owned_partial(path, identity)
        raise


def _validated_journal_identity(path: Path) -> tuple[int, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise JournalError("operation journal is unavailable") from error
    try:
        information = os.fstat(descriptor)
        if (
            not stat.S_ISREG(information.st_mode)
            or information.st_uid != os.getuid()
            or stat.S_IMODE(information.st_mode) != 0o600
        ):
            raise JournalError("operation journal is unsafe")
        return information.st_dev, information.st_ino
    finally:
        os.close(descriptor)


def _unlink_owned_partial(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        information = os.lstat(path)
    except FileNotFoundError:
        return
    if (information.st_dev, information.st_ino) == identity and stat.S_ISREG(information.st_mode):
        path.unlink()


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            information = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(information.st_mode):
            raise JournalError("state path contains a symlink")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON member")
        value[key] = item
    return value
