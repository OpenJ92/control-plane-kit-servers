"""Bounded phase reporting for authoritative cpk-server source-live scenarios."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Callable, TextIO


_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_UNSAFE_MARKERS = (
    "secret://",
    "bearer ",
    "private key",
    "begin private",
    "password",
)
_KEY_STATUSES = frozenset({"active", "verify-only", "retired", "revoked"})
_ACCESS_PATHS = frozenset({"runtime-private", "named-public-ingress"})
_COMPONENT_HEALTH = frozenset(
    {"unknown", "starting", "healthy", "degraded", "unhealthy", "absent"}
)
_RESOURCE_STAGES = frozenset(
    {"planned", "creating", "active", "removing", "removed", "uncertain"}
)


class SourceLiveInvariantError(RuntimeError):
    """A bounded authoritative acceptance failure."""

    def __init__(self, code: str) -> None:
        self.code = _bounded_name(code, field="error_code")
        super().__init__(self.code)


class SourceLiveRunFailed(RuntimeError):
    """The source-live program failed and retained its primary failure identity."""

    def __init__(self, primary_code: str, cleanup_code: str | None = None) -> None:
        self.primary_code = _bounded_name(primary_code, field="primary_code")
        self.cleanup_code = (
            _bounded_name(cleanup_code, field="cleanup_code")
            if cleanup_code is not None
            else None
        )
        message = self.primary_code
        if self.cleanup_code is not None:
            message = f"{message}; cleanup={self.cleanup_code}"
        super().__init__(message)


@dataclass(frozen=True)
class SourceLivePhaseEvidence:
    operation_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    current_graph_id: str | None = None
    key_id: str | None = None
    key_status: str | None = None
    access_path: str | None = None
    component_health: str | None = None
    resource_stage: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "operation_id",
            "session_id",
            "run_id",
            "current_graph_id",
            "key_id",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _bounded_identifier(value, field=field_name)
        _closed_optional(self.key_status, _KEY_STATUSES, field="key_status")
        _closed_optional(self.access_path, _ACCESS_PATHS, field="access_path")
        _closed_optional(
            self.component_health,
            _COMPONENT_HEALTH,
            field="component_health",
        )
        _closed_optional(
            self.resource_stage,
            _RESOURCE_STAGES,
            field="resource_stage",
        )

    def descriptor(self) -> dict[str, str]:
        return {
            key: value
            for key, value in (
                ("operation_id", self.operation_id),
                ("session_id", self.session_id),
                ("run_id", self.run_id),
                ("current_graph_id", self.current_graph_id),
                ("key_id", self.key_id),
                ("key_status", self.key_status),
                ("access_path", self.access_path),
                ("component_health", self.component_health),
                ("resource_stage", self.resource_stage),
            )
            if value is not None
        }


@dataclass(frozen=True)
class SourceLivePhase:
    name: str
    component: str
    action: Callable[[], SourceLivePhaseEvidence]

    def __post_init__(self) -> None:
        _bounded_name(self.name, field="phase")
        _bounded_name(self.component, field="component")
        if not callable(self.action):
            raise TypeError("source-live phase action must be callable")


class SourceLivePhaseLedger:
    """Append-only JSON-lines evidence with a closed public shape."""

    def __init__(self, output: TextIO) -> None:
        if not hasattr(output, "write"):
            raise TypeError("source-live phase output must be writable")
        self._output = output
        self._sequence = 0

    def started(self, phase: str, *, component: str) -> None:
        self._emit(phase, component=component, status="started")

    def succeeded(
        self,
        phase: str,
        *,
        component: str,
        evidence: SourceLivePhaseEvidence | None = None,
    ) -> None:
        self._emit(
            phase,
            component=component,
            status="succeeded",
            evidence=evidence,
        )

    def failed(self, phase: str, *, component: str, error_code: str) -> None:
        self._emit(
            phase,
            component=component,
            status="failed",
            error_code=error_code,
        )

    def skipped(self, phase: str, *, component: str, error_code: str) -> None:
        self._emit(
            phase,
            component=component,
            status="skipped",
            error_code=error_code,
        )

    def _emit(
        self,
        phase: str,
        *,
        component: str,
        status: str,
        evidence: SourceLivePhaseEvidence | None = None,
        error_code: str | None = None,
    ) -> None:
        _bounded_name(phase, field="phase")
        _bounded_name(component, field="component")
        if status not in {"started", "succeeded", "failed", "skipped"}:
            raise ValueError("source-live phase status must be closed")
        if error_code is not None:
            error_code = _bounded_name(error_code, field="error_code")
        self._sequence += 1
        descriptor: dict[str, object] = {
            "schema": "cpk.source-live-phase",
            "sequence": self._sequence,
            "phase": phase,
            "status": status,
            "component": component,
        }
        if evidence is not None:
            bounded = evidence.descriptor()
            if bounded:
                descriptor["evidence"] = bounded
        if error_code is not None:
            descriptor["error_code"] = error_code
        self._output.write(
            json.dumps(descriptor, separators=(",", ":"), sort_keys=True) + "\n"
        )
        self._output.flush()


def run_source_live_phases(
    phases: tuple[SourceLivePhase, ...],
    *,
    ledger: SourceLivePhaseLedger,
    cleanup: Callable[[], None],
) -> tuple[SourceLivePhaseEvidence, ...]:
    """Run phases in order and retain failure while executing exact cleanup once."""

    completed: list[SourceLivePhaseEvidence] = []
    for index, phase in enumerate(phases):
        ledger.started(phase.name, component=phase.component)
        try:
            evidence = phase.action()
            if not isinstance(evidence, SourceLivePhaseEvidence):
                raise SourceLiveInvariantError("phase-result-malformed")
        except SourceLiveInvariantError as error:
            _finish_failed_run(
                phases,
                failed_index=index,
                primary_code=error.code,
                ledger=ledger,
                cleanup=cleanup,
            )
        except Exception:
            _finish_failed_run(
                phases,
                failed_index=index,
                primary_code="unexpected-error",
                ledger=ledger,
                cleanup=cleanup,
            )
        ledger.succeeded(
            phase.name,
            component=phase.component,
            evidence=evidence,
        )
        completed.append(evidence)
    return tuple(completed)


def _finish_failed_run(
    phases: tuple[SourceLivePhase, ...],
    *,
    failed_index: int,
    primary_code: str,
    ledger: SourceLivePhaseLedger,
    cleanup: Callable[[], None],
) -> None:
    failed_phase = phases[failed_index]
    ledger.failed(
        failed_phase.name,
        component=failed_phase.component,
        error_code=primary_code,
    )
    for phase in phases[failed_index + 1 :]:
        ledger.skipped(
            phase.name,
            component=phase.component,
            error_code="prior-phase-failed",
        )

    cleanup_code: str | None = None
    ledger.started("abort-cleanup", component="cpk-server")
    try:
        cleanup()
    except SourceLiveInvariantError as error:
        cleanup_code = error.code
    except Exception:
        cleanup_code = "unexpected-cleanup-error"
    if cleanup_code is None:
        ledger.succeeded(
            "abort-cleanup",
            component="cpk-server",
            evidence=SourceLivePhaseEvidence(resource_stage="removed"),
        )
    else:
        ledger.failed(
            "abort-cleanup",
            component="cpk-server",
            error_code=cleanup_code,
        )
    raise SourceLiveRunFailed(primary_code, cleanup_code)


def _bounded_name(value: str, *, field: str) -> str:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded identifier")
    return value


def _bounded_identifier(value: str, *, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded identifier")
    lowered = value.lower()
    if any(marker in lowered for marker in _UNSAFE_MARKERS):
        raise ValueError(f"{field} must not contain secret-shaped material")
    return value


def _closed_optional(
    value: str | None,
    allowed: frozenset[str],
    *,
    field: str,
) -> None:
    if value is not None and value not in allowed:
        raise ValueError(f"{field} must be closed")
