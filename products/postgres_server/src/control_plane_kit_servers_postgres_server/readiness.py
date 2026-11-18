"""Bounded native PostgreSQL readiness observation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
from threading import Lock, Semaphore
import time
from typing import Callable, Mapping

from control_plane_kit_core import NodeHealthReadOutcome

MAX_PASSWORD_BYTES = 4096
MAX_OUTPUT_BYTES = 64
PROBE_SECONDS = 5.0
REAP_SECONDS = 1.0


class PasswordFileError(ValueError):
    """The fixed secret file does not satisfy the wrapper contract."""


class ProductState(Enum):
    NOT_STARTED = "not-started"
    RUNNING = "running"
    STOPPING = "stopping"
    EXITED = "exited"
    FATAL = "fatal"


@dataclass(frozen=True, slots=True)
class PsqlInvocation:
    argv: tuple[str, ...]
    environ: Mapping[str, str]


def _owner_uid(status: os.stat_result) -> int:
    return status.st_uid


def read_password(path: str | Path, *, expected_uid: int = 70) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(
            os.fspath(path), os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        )
        status = os.fstat(descriptor)
        if (not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o400
                or _owner_uid(status) != expected_uid or status.st_size > MAX_PASSWORD_BYTES):
            raise ValueError
        content = os.read(descriptor, MAX_PASSWORD_BYTES + 1)
        if len(content) > MAX_PASSWORD_BYTES:
            raise ValueError
        content = content.rstrip(b"\n")
        if not content or b"\x00" in content:
            raise ValueError
        return content
    except (OSError, ValueError):
        failure = PasswordFileError("PostgreSQL password file is invalid")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    raise failure


def psql_invocation(password: bytes) -> PsqlInvocation:
    try:
        secret = password.decode("utf-8")
    except UnicodeDecodeError:
        raise PasswordFileError("PostgreSQL password file is invalid") from None
    return PsqlInvocation((
        "/usr/local/bin/psql", "-X", "--no-psqlrc", "-h", "127.0.0.1", "-p", "5432",
        "-U", "cpk", "-d", "cpk", "-tA", "--quiet", "-c",
        "SET statement_timeout = '2s'; SELECT 1;",
    ), {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "PGPASSWORD": secret, "PGCONNECT_TIMEOUT": "2"})


def classify_psql(returncode: int, output: bytes) -> NodeHealthReadOutcome:
    if returncode != 0:
        return NodeHealthReadOutcome.UNKNOWN
    if len(output) > MAX_OUTPUT_BYTES:
        return NodeHealthReadOutcome.UNKNOWN
    if output == b"1\n":
        return NodeHealthReadOutcome.HEALTHY
    return NodeHealthReadOutcome.UNHEALTHY


def _spawn(invocation: PsqlInvocation):
    return subprocess.Popen(invocation.argv, env=dict(invocation.environ), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)


class ReadinessController:
    def __init__(self, *, password: bytes, spawn: Callable = _spawn):
        self._password = password
        self._spawn = spawn
        self._slot = Semaphore(1)
        self._lock = Lock()
        self._terminate_lock = Lock()
        self._state = ProductState.NOT_STARTED
        self._active = None

    def set_state(self, state: ProductState) -> None:
        with self._lock:
            self._state = state

    @property
    def state(self) -> ProductState:
        with self._lock:
            return self._state

    def inspect(self) -> NodeHealthReadOutcome:
        before = self.state
        if before in (ProductState.STOPPING, ProductState.EXITED):
            return NodeHealthReadOutcome.UNHEALTHY
        if before is ProductState.FATAL:
            return NodeHealthReadOutcome.UNKNOWN
        if not self._slot.acquire(blocking=False):
            return NodeHealthReadOutcome.UNKNOWN
        process = None
        release_slot = True
        try:
            with self._lock:
                if self._state is not ProductState.RUNNING:
                    return NodeHealthReadOutcome.UNHEALTHY
                process = self._spawn(psql_invocation(self._password))
                self._active = process
            outcome = self._observe(process)
            after = self.state
            if after in (ProductState.STOPPING, ProductState.EXITED):
                return NodeHealthReadOutcome.UNHEALTHY
            if after is not ProductState.RUNNING:
                return NodeHealthReadOutcome.UNKNOWN
            return outcome
        except Exception:
            return NodeHealthReadOutcome.UNKNOWN
        finally:
            if process is not None:
                try:
                    reaped = process.poll() is not None
                except Exception:
                    reaped = False
                if not reaped:
                    reaped = self._terminate(process)
                if not reaped:
                    release_slot = False
            if release_slot:
                with self._lock:
                    if self._active is process:
                        self._active = None
                self._slot.release()

    def stop_active(self, *, deadline: float | None = None) -> bool:
        with self._lock:
            process = self._active
        if process is None or process.poll() is not None:
            return True
        return self._terminate(process, deadline=deadline)

    def _observe(self, process) -> NodeHealthReadOutcome:
        output = bytearray()
        deadline = time.monotonic() + PROBE_SECONDS
        if process.stdout is None:
            return NodeHealthReadOutcome.UNKNOWN
        selector = selectors.DefaultSelector()
        try:
            selector.register(process.stdout, selectors.EVENT_READ)
            while process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._terminate(process)
                    return NodeHealthReadOutcome.UNKNOWN
                events = selector.select(remaining)
                if events:
                    chunk = os.read(process.stdout.fileno(), MAX_OUTPUT_BYTES + 1 - len(output))
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_OUTPUT_BYTES:
                        self._terminate(process)
                        return NodeHealthReadOutcome.UNKNOWN
            if process.poll() is None:
                try:
                    process.wait(timeout=max(0.0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    self._terminate(process)
                    return NodeHealthReadOutcome.UNKNOWN
            while len(output) <= MAX_OUTPUT_BYTES:
                chunk = os.read(process.stdout.fileno(), MAX_OUTPUT_BYTES + 1 - len(output))
                if not chunk:
                    break
                output.extend(chunk)
            return classify_psql(process.returncode, bytes(output))
        finally:
            selector.close()

    def _terminate(self, process, *, deadline: float | None = None) -> bool:
        def timeout() -> float:
            if deadline is None:
                return REAP_SECONDS
            return min(REAP_SECONDS, max(0.0, deadline - time.monotonic()))

        with self._terminate_lock:
            try:
                if process.poll() is not None:
                    return True
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=timeout())
                return True
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=timeout())
                    return True
                except Exception:
                    self.set_state(ProductState.FATAL)
                    return False
            except ProcessLookupError:
                return process.poll() is not None
            except Exception:
                self.set_state(ProductState.FATAL)
                return False
