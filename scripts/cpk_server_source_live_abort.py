"""Bounded abort-compensation support for cpk-server source-live scenarios.

This module is test-harness safety, not deployment policy. Authoritative cleanup
is supplied by a cpk-server workflow. Concrete emergency compensators are used
only after that workflow fails and never turn the failed scenario into success.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Callable, Mapping
from urllib.parse import urlsplit


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_SECRET_PROVIDER_ID = re.compile(r"[a-z][a-z0-9-]{0,62}\Z")
_SECRET_REFERENCE_SEGMENT = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
_MAX_SECRET_REFERENCE_BYTES = 256


class SourceLiveAbortError(RuntimeError):
    """Bounded source-live abort or cleanup failure."""


@dataclass(frozen=True)
class SourceLiveCheckpoint:
    workspace_id: str
    phase: str
    current_graph_id: str
    desired_graph_id: str

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
                raise SourceLiveAbortError(f"checkpoint {name} is invalid")


@dataclass(frozen=True)
class ExactOwnedIngressResource:
    provider_kind: str
    ingress_id: str
    epoch: int
    public_provider_coordinates: Mapping[str, str]
    source_run_id: str
    secret_reference: str
    provider_version_id: str
    provider_version_number: int

    def __post_init__(self) -> None:
        for name in (
            "provider_kind",
            "ingress_id",
            "source_run_id",
            "provider_version_id",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 255:
                raise SourceLiveAbortError(f"owned resource {name} is invalid")
        coordinates = dict(self.public_provider_coordinates)
        if not coordinates:
            raise SourceLiveAbortError("owned provider coordinates are empty")
        for key, value in coordinates.items():
            if _IDENTIFIER.fullmatch(key) is None:
                raise SourceLiveAbortError("owned provider coordinate key is invalid")
            if not isinstance(value, str) or not value or len(value) > 255:
                raise SourceLiveAbortError(
                    "owned provider coordinate value is invalid"
                )
        object.__setattr__(
            self,
            "public_provider_coordinates",
            MappingProxyType(coordinates),
        )
        if not _is_bounded_secret_reference(self.secret_reference):
            raise SourceLiveAbortError("owned resource secret reference is invalid")
        if type(self.epoch) is not int or self.epoch < 1:
            raise SourceLiveAbortError("owned resource epoch is invalid")
        if (
            type(self.provider_version_number) is not int
            or self.provider_version_number < 1
        ):
            raise SourceLiveAbortError(
                "owned resource provider version number is invalid"
            )

    def bounded_descriptor(self) -> dict[str, object]:
        return {
            "provider_kind": self.provider_kind,
            "ingress_id": self.ingress_id,
            "epoch": self.epoch,
            "public_provider_coordinates": dict(self.public_provider_coordinates),
            "source_run_id": self.source_run_id,
            "provider_version_id": self.provider_version_id,
            "provider_version_number": self.provider_version_number,
        }


def _is_bounded_secret_reference(candidate: object) -> bool:
    if not isinstance(candidate, str):
        return False
    try:
        encoded = candidate.encode("utf-8")
    except UnicodeEncodeError:
        return False
    if len(encoded) > _MAX_SECRET_REFERENCE_BYTES:
        return False
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return False
    path = tuple(part for part in parsed.path.split("/") if part)
    return (
        candidate == f"secret://{parsed.netloc}{parsed.path}"
        and parsed.scheme == "secret"
        and _SECRET_PROVIDER_ID.fullmatch(parsed.netloc) is not None
        and not parsed.query
        and not parsed.fragment
        and bool(path)
        and parsed.path == "/" + "/".join(path)
        and all(
            part not in (".", "..")
            and _SECRET_REFERENCE_SEGMENT.fullmatch(part) is not None
            for part in path
        )
    )


@dataclass(frozen=True)
class AbortCompensationReport:
    authoritative: bool
    emergency_attempted: bool
    resource_count: int


EmergencyCompensator = Callable[[ExactOwnedIngressResource], tuple[str, ...]]


def record_checkpoint(
    path: Path,
    checkpoint: SourceLiveCheckpoint,
    *,
    fail_after_phase: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(checkpoint), separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
    if fail_after_phase == checkpoint.phase:
        raise SourceLiveAbortError(
            f"source-live fault injected after phase {checkpoint.phase}"
        )


def read_checkpoint(path: Path) -> SourceLiveCheckpoint:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise SourceLiveAbortError("source-live checkpoint is unavailable") from None
    if not isinstance(document, dict):
        raise SourceLiveAbortError("source-live checkpoint is malformed")
    try:
        return SourceLiveCheckpoint(
            workspace_id=document["workspace_id"],
            phase=document["phase"],
            current_graph_id=document["current_graph_id"],
            desired_graph_id=document["desired_graph_id"],
        )
    except (KeyError, TypeError, SourceLiveAbortError):
        raise SourceLiveAbortError("source-live checkpoint is malformed") from None


def compensate_abort(
    *,
    authoritative_cleanup: Callable[[], None],
    verify_authoritative_absence: Callable[[], None],
    verify_emergency_absence: Callable[[], None],
    resources: tuple[ExactOwnedIngressResource, ...],
    emergency_resources: tuple[ExactOwnedIngressResource, ...],
    emergency_compensators: Mapping[str, EmergencyCompensator],
) -> AbortCompensationReport:
    if any(resource not in resources for resource in emergency_resources):
        raise SourceLiveAbortError("emergency cleanup evidence is incongruent")
    try:
        authoritative_cleanup()
    except Exception:
        pass
    absence_failed = False
    try:
        verify_authoritative_absence()
    except Exception:
        absence_failed = True
    if not absence_failed:
        return AbortCompensationReport(
            authoritative=True,
            emergency_attempted=False,
            resource_count=len(resources),
        )

    failed: list[str] = []
    for resource in emergency_resources:
        compensator = emergency_compensators.get(resource.provider_kind)
        if compensator is None:
            failed.append(f"provider:{resource.provider_kind}")
            continue
        for stage in compensator(resource):
            failed.append(f"{resource.provider_kind}:{stage}")
    emergency_absence_failed = False
    try:
        verify_emergency_absence()
    except Exception:
        emergency_absence_failed = True
    if emergency_absence_failed:
        failed.append("absence-verification")
    if failed or not emergency_resources:
        categories = failed or ["unproven-emergency-authority"]
        raise SourceLiveAbortError(
            "source-live exact cleanup is uncertain: " + ",".join(categories)
        )
    return AbortCompensationReport(
        authoritative=False,
        emergency_attempted=True,
        resource_count=len(resources),
    )
