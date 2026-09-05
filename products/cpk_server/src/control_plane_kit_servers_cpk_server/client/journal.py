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
    if not all(isinstance(item, str) and item for item in target.values()):
        raise JournalError("operation journal target is invalid")
    if not isinstance(value["desired"], dict):
        raise JournalError("operation journal desired reference is invalid")
    if not isinstance(value["phase"], str) or not value["phase"]:
        raise JournalError("operation journal phase is invalid")
    if value["pending_request"] is not None and not isinstance(value["pending_request"], dict):
        raise JournalError("operation journal pending request is invalid")
    if not isinstance(value["coordinates"], dict):
        raise JournalError("operation journal coordinates are invalid")
    history = value["request_history"]
    if not isinstance(history, list) or len(history) > MAXIMUM_REQUEST_RECORDS:
        raise JournalError("operation journal request budget is exhausted")
    if value["last_result"] is not None and not isinstance(value["last_result"], dict):
        raise JournalError("operation journal result is invalid")


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
