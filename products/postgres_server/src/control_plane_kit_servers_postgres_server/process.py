"""Non-root PID1 coordinator for PostgreSQL and its protected management host."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
from threading import Event, Lock, Thread, get_native_id
import time
from typing import Callable

from .configuration import (PGDATA, PASSWORD_PATH, PostgresConfigurationError,
                            postgres_control_configuration_artifact, read_postgres_control_configuration)
from .readiness import PasswordFileError, ProductState, ReadinessController, read_password
from .server import create_management_server

STOP_SECONDS = 8.0
FINAL_REAP_SECONDS = 1.0
START_SECONDS = 3.0
MAX_STARTUP_FDS = 256
MAX_STARTUP_TCP_BYTES = 256 * 1024
MAX_STARTUP_TCP_LINE = 4096
ENTRYPOINT = "/usr/local/bin/docker-entrypoint.sh"
LIFECYCLE_PREFIX = "postgres-server lifecycle "
ROLE_PREFIX = "postgres-server roles "
ROLE_PID_FIELDS = ("owner_pid", "child_entrypoint_pid", "management_native_id")
ROLE_STATE_FIELDS = ("management_entered", "management_ended", "management_alive_at_native_exit")


def valid_role_diagnostic(value: object) -> bool:
    if type(value) is not dict or set(value) != set(ROLE_PID_FIELDS + ROLE_STATE_FIELDS):
        return False
    return all(value[key] is None or type(value[key]) is int and 1 <= value[key] <= 2147483647
               for key in ROLE_PID_FIELDS) and all(
        value[key] is None or type(value[key]) is bool for key in ROLE_STATE_FIELDS)


def emit_role_diagnostic(coordinator, *, stream=None) -> None:
    try:
        value = coordinator.role_diagnostic
        if valid_role_diagnostic(value):
            print(ROLE_PREFIX + json.dumps(value, separators=(",", ":"), sort_keys=True),
                  file=sys.stderr if stream is None else stream, flush=True)
    except Exception:
        return


def _bounded_pid(value: object) -> int | None:
    return value if type(value) is int and 1 <= value <= 2147483647 else None


def _observe_role_pid(read: Callable[[], object]) -> int | None:
    """Unavailable diagnostic identity is null, never a lifecycle failure."""
    try:
        return _bounded_pid(read())
    except Exception:
        return None


class PostgresProcessError(RuntimeError):
    """Bounded process startup/lifecycle failure."""


class LifecycleReason(Enum):
    NATIVE_EXIT = "native_exit"
    MANAGEMENT_EXIT = "management_exit"
    READINESS_FATAL = "readiness_fatal"
    STARTUP_FAILURE = "startup_failure"


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    reason: LifecycleReason
    native_exit_code: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reason, LifecycleReason):
            raise ValueError("PostgreSQL lifecycle reason is invalid")
        if self.reason is LifecycleReason.NATIVE_EXIT:
            if type(self.native_exit_code) is not int:
                raise ValueError("PostgreSQL native exit code is invalid")
        elif self.native_exit_code is not None:
            raise ValueError("PostgreSQL lifecycle record is invalid")

    def payload(self) -> dict[str, str | int | None]:
        return {"reason": self.reason.value, "native_exit_code": self.native_exit_code}


def emit_lifecycle_record(record: LifecycleRecord, *, stream=None) -> None:
    try:
        target = sys.stderr if stream is None else stream
        encoded = json.dumps(record.payload(), separators=(",", ":"), sort_keys=True)
        print(LIFECYCLE_PREFIX + encoded, file=target, flush=True)
    except Exception:
        return


def _owner_uid(status: os.stat_result) -> int:
    return status.st_uid


def validate_pgdata(path: str | Path = PGDATA, *, expected_uid: int = 70) -> None:
    try:
        status = os.lstat(path)
        if not stat.S_ISDIR(status.st_mode) or _owner_uid(status) != expected_uid:
            raise ValueError
    except (OSError, ValueError):
        raise PostgresProcessError("PostgreSQL data directory is invalid") from None


def _spawn_native(argv: tuple[str, ...], **kwargs):
    return subprocess.Popen(argv, **kwargs)


def native_listener_observed(
    child_pid: int, *, proc_root: Path = Path("/proc"),
    native_executable: Path = Path("/usr/local/bin/postgres"),
    cancelled: Callable[[], bool] = lambda: False,
) -> bool:
    """Observe the known child's listener metadata; never read descriptor contents.

    This is a sampled ownership milestone for the maintained trusted entrypoint,
    not socket-creation attestation or SQL health. The caller owns child reaping.
    """
    if cancelled():
        return False
    if _bounded_pid(child_pid) is None:
        raise PostgresProcessError("PostgreSQL startup observation unavailable")
    child = proc_root / str(child_pid)
    try:
        expected = os.stat(native_executable)

        def native_identity() -> bool:
            actual = os.stat(child / "exe")
            return (actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino)

        if not native_identity():
            return False
        sockets = {}
        with os.scandir(child / "fd") as entries:
            for count, entry in enumerate(entries, start=1):
                if cancelled():
                    return False
                if count > MAX_STARTUP_FDS:
                    raise PostgresProcessError("PostgreSQL startup observation exceeds bounds")
                try:
                    link = os.readlink(entry.path)
                except FileNotFoundError:
                    continue
                match = re.fullmatch(r"socket:\[([1-9][0-9]{0,19})\]", link)
                if match is not None:
                    sockets[match[1]] = entry.path
        if cancelled() or not sockets:
            return False
        with open(child / "net" / "tcp", "rb") as table:
            header = table.readline(MAX_STARTUP_TCP_LINE + 1)
            if len(header) > MAX_STARTUP_TCP_LINE or header.split()[:4] != [
                b"sl", b"local_address", b"rem_address", b"st"
            ]:
                raise PostgresProcessError("PostgreSQL startup observation is invalid")
            total = len(header)
            while not cancelled():
                row = table.readline(MAX_STARTUP_TCP_LINE + 1)
                if not row:
                    return False
                total += len(row)
                if len(row) > MAX_STARTUP_TCP_LINE or total > MAX_STARTUP_TCP_BYTES:
                    raise PostgresProcessError("PostgreSQL startup observation exceeds bounds")
                fields = row.split()
                if (len(fields) < 10
                        or re.fullmatch(rb"[0-9A-F]{8}:[0-9A-F]{4}", fields[1]) is None
                        or re.fullmatch(rb"[0-9A-F]{2}", fields[3]) is None
                        or re.fullmatch(rb"[0-9]{1,20}", fields[9]) is None):
                    raise PostgresProcessError("PostgreSQL startup observation is invalid")
                inode = fields[9].decode("ascii")
                descriptor = sockets.get(inode)
                if (descriptor is not None and fields[3] == b"0A"
                        and fields[1] in (b"00000000:1538", b"0100007F:1538")):
                    try:
                        still_owned = os.readlink(descriptor) == f"socket:[{inode}]"
                    except FileNotFoundError:
                        return False
                    return still_owned and native_identity() and not cancelled()
        return False
    except OSError:
        raise PostgresProcessError("PostgreSQL startup observation unavailable") from None


class PostgresCoordinator:
    def __init__(self, host, readiness: ReadinessController, *, spawn: Callable = _spawn_native):
        self.host = host
        self.readiness = readiness
        self._spawn = spawn
        self._native = None
        self._serve_thread = None
        self._serve_failed = Event()
        self._stop_requested = Event()
        self._stop_lock = Lock()
        self._stop_complete = Event()
        self._lifecycle_lock = Lock()
        self._lifecycle_record = None
        self._stopped = False
        self._stop_result = 1
        self._management_live = False
        self._child_entrypoint_pid = None
        self._management_native_id = None
        self._management_entered = False
        self._management_ended = False
        self._role_diagnostic = None

    @property
    def role_diagnostic(self) -> dict | None:
        return None if self._role_diagnostic is None else dict(self._role_diagnostic)

    def _observe_roles_at_native_exit(self) -> None:
        # Per-field observations before cleanup, not an atomic/lock-time snapshot.
        owner_pid = _observe_role_pid(os.getpid)
        try:
            alive = None if self._serve_thread is None else self._serve_thread.is_alive()
        except Exception:
            alive = None
        self._role_diagnostic = {
            "owner_pid": owner_pid,
            "child_entrypoint_pid": self._child_entrypoint_pid,
            "management_native_id": self._management_native_id,
            "management_entered": self._management_entered,
            "management_ended": self._management_ended,
            "management_alive_at_native_exit": alive,
        }

    @property
    def lifecycle_record(self) -> LifecycleRecord | None:
        with self._lifecycle_lock:
            return self._lifecycle_record

    def _record_lifecycle(self, record: LifecycleRecord) -> None:
        with self._lifecycle_lock:
            if self._lifecycle_record is None:
                self._lifecycle_record = record

    def start_native(self) -> None:
        if self._native is not None:
            raise PostgresProcessError("PostgreSQL native child already started")
        self._native = self._spawn((ENTRYPOINT, "postgres"), start_new_session=True)
        self._child_entrypoint_pid = _observe_role_pid(lambda: self._native.pid)

    def _record_native_exit(self, returncode: int) -> None:
        self._record_lifecycle(LifecycleRecord(LifecycleReason.NATIVE_EXIT, returncode))
        try:
            self._observe_roles_at_native_exit()
        except Exception:
            self._role_diagnostic = None

    def wait_for_native_listener(self) -> bool:
        """No auxiliary tasks or aggregate initialization deadline before admission."""
        if self._native is None:
            raise PostgresProcessError("PostgreSQL native child is not started")
        while True:
            returncode = self._native.poll()
            if returncode is not None:
                self._record_native_exit(returncode)
                return False
            if self._stop_requested.is_set():
                return False
            try:
                ready = native_listener_observed(
                    self._native.pid, cancelled=self._stop_requested.is_set)
            except PostgresProcessError:
                returncode = self._native.poll()
                if returncode is not None:
                    self._record_native_exit(returncode)
                    return False
                if self._stop_requested.is_set():
                    return False
                raise
            returncode = self._native.poll()
            if returncode is not None:
                self._record_native_exit(returncode)
                return False
            if self._stop_requested.is_set():
                return False
            if ready:
                return True
            self._stop_requested.wait(0.05)

    def start_management(self) -> None:
        if self._native is None:
            raise PostgresProcessError("PostgreSQL native child is not started")

        def serve() -> None:
            self._management_entered = True
            self._management_native_id = _observe_role_pid(get_native_id)
            try:
                self.host.serve_forever(poll_interval=0.05)
            finally:
                self._management_ended = True
                self._serve_failed.set()

        thread = Thread(target=serve, name="cpk-postgres-management", daemon=True)
        self._serve_thread = thread
        thread.start()
        deadline = time.monotonic() + START_SECONDS
        while not self.host.cpk_is_serving:
            if self._serve_failed.is_set() or not thread.is_alive() or time.monotonic() >= deadline:
                raise PostgresProcessError("PostgreSQL management host failed to start")
            time.sleep(0.005)
        self._management_live = True
        self.readiness.set_state(ProductState.RUNNING)

    def request_stop(self) -> None:
        self._stop_requested.set()

    def wait(self, *, poll_seconds: float = 0.05) -> int:
        if self._native is None:
            return 1
        while True:
            returncode = self._native.poll()
            if returncode is not None:
                self._record_native_exit(returncode)
                deadline = time.monotonic() + STOP_SECONDS
                self.readiness.set_state(ProductState.STOPPING)
                self.readiness.stop_active(deadline=deadline)
                self._close_management(deadline)
                self.readiness.set_state(ProductState.EXITED)
                return 1
            if self._serve_failed.is_set():
                self._record_lifecycle(LifecycleRecord(LifecycleReason.MANAGEMENT_EXIT))
                return self.stop(failure=True)
            if self.readiness.state is ProductState.FATAL:
                self._record_lifecycle(LifecycleRecord(LifecycleReason.READINESS_FATAL))
                return self.stop(failure=True)
            if self._stop_requested.wait(poll_seconds):
                return self.stop()

    def stop(self, *, failure: bool = False) -> int:
        with self._stop_lock:
            if self._stopped:
                first = False
            else:
                first = True
                self._stopped = True
        if not first:
            self._stop_complete.wait(STOP_SECONDS + FINAL_REAP_SECONDS)
            return self._stop_result
        deadline = time.monotonic() + STOP_SECONDS
        self.request_stop()
        self.readiness.set_state(ProductState.STOPPING)
        results = {"probe": False, "management": False, "native": False}

        def cleanup(name: str, operation: Callable[[], bool]) -> None:
            try:
                results[name] = bool(operation())
            except BaseException:
                results[name] = False

        operations = (
            ("native", lambda: self._stop_native(deadline)),
            ("probe", lambda: self.readiness.stop_active(deadline=deadline)),
            ("management", lambda: self._close_management(deadline)),
        )
        workers = []
        if self._serve_thread is None:
            # Native startup may still be checking a retained lock PID. Do not
            # allocate competing task IDs, even to clean up a cancelled start.
            for name, operation in operations:
                cleanup(name, operation)
        else:
            workers = [Thread(target=cleanup, args=item, daemon=True) for item in operations]
            for worker in workers:
                worker.start()
            completion_deadline = deadline + FINAL_REAP_SECONDS
            for worker in workers:
                worker.join(max(0.0, completion_deadline - time.monotonic()))
        clean = all(results.values()) and all(not worker.is_alive() for worker in workers)
        self.readiness.set_state(ProductState.EXITED)
        self._stop_result = 0 if not failure and clean else 1
        self._stop_complete.set()
        return self._stop_result

    def _close_management(self, deadline: float) -> bool:
        if self.host is None:
            return True
        result = True
        if self._management_live and getattr(self.host, "cpk_is_serving", False):
            completed = Event()

            def shutdown() -> None:
                try:
                    self.host.shutdown()
                except BaseException:
                    nonlocal result
                    result = False
                finally:
                    completed.set()

            worker = Thread(target=shutdown, name="cpk-postgres-management-stop", daemon=True)
            worker.start()
            completed.wait(max(0.0, deadline - time.monotonic()))
            if not completed.is_set():
                result = False
        try:
            self.host.server_close()
        except BaseException:
            result = False
        thread = self._serve_thread
        if thread is not None:
            thread.join(max(0.0, deadline - time.monotonic()))
            if thread.is_alive():
                result = False
        self._management_live = False
        return result

    def _stop_native(self, deadline: float) -> bool:
        child = self._native
        if child is None:
            return True
        returncode = child.poll()
        if returncode is not None:
            return returncode == 0
        try:
            os.killpg(child.pid, signal.SIGINT)
            return child.wait(timeout=max(0.0, deadline - time.monotonic())) == 0
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=FINAL_REAP_SECONDS)
                return False
            except BaseException:
                return False
        except BaseException:
            return False


def main() -> int:
    coordinator = None
    startup_complete = False
    try:
        if os.getuid() != 70 or os.getgid() != 70:
            raise PostgresProcessError("PostgreSQL wrapper requires uid and gid 70")
        validate_pgdata()
        password_path = os.environ.get("POSTGRES_PASSWORD_FILE", PASSWORD_PATH)
        if password_path != PASSWORD_PATH:
            raise PostgresProcessError("PostgreSQL password path is invalid")
        password = read_password(password_path)
        configuration = read_postgres_control_configuration()
        postgres_control_configuration_artifact(configuration)
        readiness = ReadinessController(password=password)
        coordinator = PostgresCoordinator(None, readiness)

        def stop_signal(signum, frame) -> None:  # noqa: ANN001
            coordinator.request_stop()

        signal.signal(signal.SIGINT, stop_signal)
        signal.signal(signal.SIGTERM, stop_signal)
        coordinator.start_native()
        if coordinator.wait_for_native_listener():
            coordinator.host = create_management_server(configuration, readiness)
            coordinator.start_management()
        startup_complete = True
        result = coordinator.wait()
        record = coordinator.lifecycle_record
        if result != 0 and record is not None:
            emit_lifecycle_record(record)
            emit_role_diagnostic(coordinator)
        return result
    except (PostgresConfigurationError, PasswordFileError, PostgresProcessError, OSError):
        record = None
        if not startup_complete:
            record = LifecycleRecord(LifecycleReason.STARTUP_FAILURE)
        elif coordinator is not None:
            record = coordinator.lifecycle_record
        if record is not None:
            emit_lifecycle_record(record)
        if coordinator is not None:
            coordinator.stop(failure=True)
        print("postgres-server startup or lifecycle failure", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
