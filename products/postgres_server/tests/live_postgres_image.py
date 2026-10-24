"""One-shot source-image witness; invoked only by the repository Docker gate."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import re
import socket
import time
import runpy

import docker

from postgres_control_fixtures import fixture, health_token, readiness_only
from control_plane_kit_servers_postgres_server.configuration import postgres_control_configuration_artifact
from control_plane_kit_servers_postgres_server.process import LIFECYCLE_PREFIX


RUN = os.environ["CPK_POSTGRES_TEST_RUN"]
HOST_RECORDS = Path(os.environ["CPK_POSTGRES_HOST_RECORDS"])
RECORDS = Path("/witness")
LABELS = {"org.openj92.cpk.test-run": RUN, "org.openj92.project": "control-plane-kit-servers"}
PASSWORD = "postgres-source-witness-password"
MAX_FAILURE_LOG_BYTES = 65536

FAILURE_LOG_MARKERS = {
    "wrapper_failure": b"postgres-server startup or lifecycle failure",
    "native_lock_refusal": b"lock file \"postmaster.pid\" already exists",
    "native_interrupted": b"database system was interrupted",
    "native_ready": b"database system is ready to accept connections",
    "native_fatal": b"FATAL:",
    "native_panic": b"PANIC:",
}
LIFECYCLE_REASONS = {"native_exit", "management_exit", "readiness_fatal", "startup_failure"}


def scan_refused_lock_pid(logs: bytes, *, truncated: bool = False) -> dict[str, object]:
    """Project a native hint, never a process owner or inferred failure cause."""
    result = {"lock_pid_status": "absent", "refused_lock_pid": None}
    if truncated or len(logs) > MAX_FAILURE_LOG_BYTES:
        return dict(result, lock_pid_status="truncated")
    lines = logs.splitlines()
    # The Docker tail may have discarded earlier matches. Do not claim uniqueness
    # when the requested line limit is reached, even if exactly 128 lines existed.
    if len(lines) >= 128:
        return dict(result, lock_pid_status="truncated")
    hints = [(index, line) for index, line in enumerate(lines) if b"Is another " in line]
    refusals = [(index, line) for index, line in enumerate(lines)
                if FAILURE_LOG_MARKERS["native_lock_refusal"] in line]
    if not hints:
        return result
    if len(hints) != 1 or hints[0][1].count(b"Is another ") != 1 or len(refusals) > 1:
        return dict(result, lock_pid_status="ambiguous")
    if len(refusals) != 1 or hints[0][0] != refusals[0][0] + 1:
        return dict(result, lock_pid_status="invalid")
    line, refusal = hints[0][1], refusals[0][1]
    if any(len(value) > 1024 or any(byte < 32 or byte > 126 for byte in value)
           for value in (line, refusal)):
        return dict(result, lock_pid_status="invalid")
    # Selected native default stderr prefix: UTC timestamp and emitting PID.
    # Other formats are unknown, never searched for an embedded HINT substring.
    prefix = (rb'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}'
              rb'(?:\.[0-9]{3})? UTC \[([1-9][0-9]{0,9})\] ')
    fatal = re.fullmatch(prefix + rb'FATAL: +lock file "postmaster\.pid" already exists', refusal)
    match = re.fullmatch(
        prefix + rb'HINT: +Is another (?:postmaster|postgres) \(PID ([1-9][0-9]{0,9})\) '
        rb'running in data directory "[^"\r\n]*"\?', line,
    )
    if fatal is None or match is None or fatal.group(1) != match.group(1):
        return dict(result, lock_pid_status="invalid")
    pid = int(match.group(2))
    if pid > 2147483647 or int(match.group(1)) > 2147483647:
        return dict(result, lock_pid_status="invalid")
    return {"lock_pid_status": "one", "refused_lock_pid": pid}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def scan_lifecycle_record(logs: bytes) -> dict[str, object]:
    result = {
        "lifecycle_record_present": False,
        "lifecycle_record_valid": False,
        "lifecycle_record_ambiguous": False,
        "lifecycle_reason": None,
        "native_exit_code": None,
    }
    prefix = LIFECYCLE_PREFIX.encode("ascii")
    records = tuple(line[len(prefix):] for line in logs.splitlines() if line.startswith(prefix))
    if not records:
        return result
    result["lifecycle_record_present"] = True
    if len(records) != 1:
        result["lifecycle_record_ambiguous"] = True
        return result

    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate lifecycle key")
            value[key] = item
        return value

    try:
        value = json.loads(records[0], object_pairs_hook=reject_duplicates)
        if type(value) is not dict or set(value) != {"reason", "native_exit_code"}:
            raise ValueError
        reason = value["reason"]
        code = value["native_exit_code"]
        if type(reason) is not str or reason not in LIFECYCLE_REASONS:
            raise ValueError
        if reason == "native_exit":
            if type(code) is not int:
                raise ValueError
        elif code is not None:
            raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        result["lifecycle_record_ambiguous"] = True
        return result
    result.update({
        "lifecycle_record_valid": True,
        "lifecycle_reason": reason,
        "native_exit_code": code,
    })
    return result


def raise_container_failure(container, message: str) -> None:
    state_refresh_available = False
    state = {}
    try:
        container.reload()
        observed = container.attrs.get("State", {})
        state = observed if isinstance(observed, dict) else {}
        state_refresh_available = True
    except Exception:
        state = {}
        state_refresh_available = False
    logs_unavailable = False
    try:
        logs = container.logs(stdout=True, stderr=True, tail=128)
        if isinstance(logs, str):
            logs = logs.encode("utf-8", errors="replace")
        elif not isinstance(logs, bytes):
            logs = bytes(logs)
    except Exception:
        logs = b""
        logs_unavailable = True
    logs_truncated = len(logs) > MAX_FAILURE_LOG_BYTES
    logs = logs[-MAX_FAILURE_LOG_BYTES:]
    try:
        lock_pid = (dict(lock_pid_status="unavailable", refused_lock_pid=None)
                    if logs_unavailable else scan_refused_lock_pid(logs, truncated=logs_truncated))
    except Exception:
        lock_pid = dict(lock_pid_status="invalid", refused_lock_pid=None)
    if state_refresh_available:
        error = str(state.get("Error", "")).encode("utf-8", errors="replace")
        state_values = {
            "status": str(state.get("Status", "unknown"))[:64],
            "exit_code": state.get("ExitCode"),
            "oom_killed": state.get("OOMKilled") is True,
            "daemon_error_present": bool(error),
            "daemon_error_sha256": hashlib.sha256(error).hexdigest(),
        }
    else:
        state_values = {
            "status": None,
            "exit_code": None,
            "oom_killed": None,
            "daemon_error_present": None,
            "daemon_error_sha256": None,
        }
    try:
        lifecycle = scan_lifecycle_record(logs)
    except Exception:
        present = any(
            line.startswith(LIFECYCLE_PREFIX.encode("ascii")) for line in logs.splitlines()
        )
        lifecycle = {
            "lifecycle_record_present": present,
            "lifecycle_record_valid": False,
            "lifecycle_record_ambiguous": present,
            "lifecycle_reason": None,
            "native_exit_code": None,
        }
    event = {"postgres_source_failure": {
        "message": message,
        "state_refresh_available": state_refresh_available,
        **state_values,
        "log_tail_lines_requested": 128,
        "log_tail_bytes_retained": len(logs),
        "log_tail_bytes_truncated": logs_truncated,
        "log_tail_unavailable": logs_unavailable,
        "log_tail_sha256": hashlib.sha256(logs).hexdigest(),
        "password_present_in_retained_tail": PASSWORD.encode() in logs,
        "markers_in_retained_tail": {
            name: marker in logs for name, marker in FAILURE_LOG_MARKERS.items()
        },
        **lifecycle,
        **lock_pid,
    }}
    try:
        print(json.dumps(event, sort_keys=True), flush=True)
    except Exception:
        raise AssertionError(message) from None
    raise AssertionError(message)


def prepare_files():
    value = fixture()
    value.config = readiness_only(value.config)
    artifact = postgres_control_configuration_artifact(value.config)
    control = RECORDS / "control.json"
    secret = RECORDS / "password"
    init = RECORDS / "10-witness.sql"
    wrong_owner_data = RECORDS / "wrong-owner-data"
    control.write_text(artifact.content, encoding="utf-8")
    control.chmod(0o444)
    secret.write_text(PASSWORD + "\n", encoding="utf-8")
    secret.chmod(0o400)
    os.chown(secret, 70, 70)
    init.write_text(
        "SELECT pg_sleep(2); CREATE TABLE cpk_witness(value text NOT NULL); "
        "INSERT INTO cpk_witness VALUES ('retained-row');\n",
        encoding="utf-8",
    )
    init.chmod(0o444)
    wrong_owner_data.mkdir()
    wrong_owner_data.chmod(0o755)
    os.chown(wrong_owner_data, 0, 0)
    require(wrong_owner_data.stat().st_uid == 0, "wrong-owner bind setup was not root-owned")
    return value


def wait_running(container, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        container.reload()
        if container.status == "running":
            return
        if container.status in {"exited", "dead"}:
            raise AssertionError("PostgreSQL source container exited before running")
        time.sleep(0.1)
    raise AssertionError("PostgreSQL source container did not run")


def wait_query(
    container,
    seconds: float = 45.0,
    *,
    observe_native: bool = False,
) -> None:
    deadline = time.monotonic() + seconds
    command = ("/usr/local/bin/psql", "-X", "-U", "cpk", "-d", "cpk", "-tA", "-c",
               "SELECT value FROM cpk_witness;")
    if observe_native:
        while time.monotonic() < deadline:
            container.reload()
            if container.status != "running":
                raise_container_failure(
                    container,
                    "PostgreSQL source container exited before readiness",
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                break
            try:
                connection = socket.create_connection(
                    (container.name, 5432),
                    timeout=min(1.0, remaining),
                )
            except OSError:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    break
                time.sleep(min(0.1, remaining))
                continue
            try:
                pass
            finally:
                connection.close()
            break
    while time.monotonic() < deadline:
        container.reload()
        if container.status != "running":
            raise_container_failure(container, "PostgreSQL source container exited before readiness")
        result = container.exec_run(command, stdin=False, demux=True)
        stdout, stderr = result.output
        if result.exit_code == 0 and stdout == b"retained-row\n":
            require(not stderr, "successful retained query wrote stderr")
            return
        if observe_native:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                break
            time.sleep(min(0.25, remaining))
        else:
            time.sleep(0.25)
    raise AssertionError("PostgreSQL retained row was not queryable")


def health(container, token: str | None) -> tuple[int, dict]:
    connection = HTTPConnection(container.name, 8000, timeout=2)
    try:
        headers = {} if token is None else {"Authorization": "Bearer " + token}
        connection.request("GET", "/__control/health/readiness", headers=headers)
        response = connection.getresponse()
        body = response.read(65537)
        require(len(body) <= 65536, "management response exceeded bound")
        return response.status, {} if not body else json.loads(body)
    finally:
        connection.close()


def wait_listener_denial(container, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            status, _ = health(container, None)
            require(status == 401, "management accepted missing credential")
            return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("PostgreSQL management listener did not become available")


def wait_health(container, token: str, expected: str, seconds: float = 45.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        outcome = "transport-unavailable"
        try:
            status, body = health(container, token)
            require(status == 200, "signed readiness request was refused")
            outcome = body.get("outcome")
            require(outcome in {"healthy", "unhealthy", "unknown"}, "readiness outcome is invalid")
        except OSError:
            outcome = "transport-unavailable"
        if outcome == expected:
            return
        time.sleep(0.1)
    raise AssertionError("PostgreSQL readiness did not become " + expected)


def wait_exit(container, expected: int, seconds: float = 15.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        container.reload()
        if container.status == "exited":
            require(container.attrs["State"]["ExitCode"] == expected, "unexpected container exit")
            return
        time.sleep(0.1)
    raise AssertionError("PostgreSQL source container did not exit")


def mounts(data_source: str, *, init: bool) -> dict[str, dict[str, str]]:
    values = {
        data_source: {"bind": "/var/lib/postgresql/data", "mode": "rw"},
        str(HOST_RECORDS / "control.json"): {"bind": "/etc/cpk/postgres/control.json", "mode": "ro"},
        str(HOST_RECORDS / "password"): {"bind": "/run/secrets/postgres/password", "mode": "ro"},
    }
    if init:
        values[str(HOST_RECORDS / "10-witness.sql")] = {
            "bind": "/docker-entrypoint-initdb.d/10-witness.sql", "mode": "ro"
        }
    return values


def create(client, image_id: str, network_name: str, volume_name: str, suffix: str, *, init: bool = False):
    return client.containers.create(
        image_id,
        name=f"{RUN}-{suffix}",
        labels=LABELS,
        network=network_name,
        volumes=mounts(volume_name, init=init),
    )


def select_image(client, tag):
    mode = os.environ.get("CPK_POSTGRES_ARTIFACT_MODE", "source-built")
    names = ("CPK_POSTGRES_IMAGE", "CPK_POSTGRES_SOURCE_REVISION", "CPK_POSTGRES_RECIPE_SHA256")
    if mode == "published-digest":
        reference, source, recipe = (os.environ[name] for name in names)
        policy = runpy.run_path(str(Path(__file__).resolve().parents[1] / "release.py"))
        policy["published_reference"](reference)
        image = client.images.get(reference)
        image.reload()
        identity = policy["published_image"](image.attrs, reference, source, recipe)
        require(image.id == identity, "published image identity changed")
        return image, False
    require(mode == "source-built" and not any(name in os.environ for name in names),
            "invalid PostgreSQL artifact selection")
    image, _ = client.images.build(
        path="/source", dockerfile="products/postgres_server/Dockerfile", tag=tag,
        labels=LABELS, rm=True,
    )
    return image, True


def cleanup_image(client, image, tag, owned):
    if owned:
        image.reload()
        require(image.labels.get("org.openj92.cpk.test-run") == RUN, "foreign image cleanup refused")
        require(client.images.get(tag).id == image.id, "source image tag changed")
        client.images.remove(tag, force=True)


def cleanup_files():
    for name in ("control.json", "password", "10-witness.sql"):
        (RECORDS / name).unlink(missing_ok=True)
    directory = RECORDS / "wrong-owner-data"
    if directory.exists():
        directory.rmdir()


def require_fresh_resources(client):
    # Docker volume create may return an existing volume. Refuse adoption before
    # writing fixtures or creating anything; a new receipt path is not ownership.
    for filters in ({"label": "org.openj92.cpk.test-run=" + RUN}, {"name": RUN}):
        require(not client.containers.list(all=True, filters=filters), "existing PostgreSQL test container")
        require(not client.volumes.list(filters=filters), "existing PostgreSQL test volume")
        require(not client.networks.list(filters=filters), "existing PostgreSQL test network")


def exercise(client, image) -> None:
    require_fresh_resources(client)
    network = None
    controller = None
    controller_connected = False
    volumes = []
    containers = []
    try:
        value = prepare_files()
        image.reload()
        require(image.attrs["Config"]["User"] == "70:70", "image is not uid/gid 70")
        require(image.attrs["Config"]["Entrypoint"] in (None, []), "upstream entrypoint remains active")
        require("5432/tcp" in image.attrs["Config"]["ExposedPorts"], "native port missing")
        require("8000/tcp" in image.attrs["Config"]["ExposedPorts"], "management port missing")

        network = client.networks.create(f"{RUN}-network", internal=True, labels=LABELS)
        controller = client.containers.get(os.environ["HOSTNAME"])
        network.connect(controller)
        controller_connected = True
        data = client.volumes.create(name=f"{RUN}-data", labels=LABELS)
        volumes.append(data)

        issued = int(time.time()) - 1
        _, valid = health_token(value, issued_at=issued)
        wrong_target = replace(value.config.target, receiver_id="f" * 32)
        _, wrong = health_token(value, issued_at=issued, request_changes={"target": wrong_target})

        first = create(client, image.id, network.name, data.name, "first", init=True)
        containers.append(first)
        first.start()
        wait_running(first)
        wait_listener_denial(first)
        require(health(first, wrong)[0] == 401, "management accepted mismatched credential")
        wait_health(first, valid, "unknown")
        wait_query(first)
        wait_health(first, valid, "healthy")
        require(first.attrs["HostConfig"]["Binds"] is not None, "expected fixed mounts")
        require("docker.sock" not in repr(first.attrs["Mounts"]), "Docker socket reached product")
        first.stop(timeout=10)
        wait_exit(first, 0)
        require(PASSWORD.encode() not in first.logs(stdout=True, stderr=True), "password reached logs")
        first.remove()
        containers.remove(first)

        restarted = create(client, image.id, network.name, data.name, "restart")
        containers.append(restarted)
        restarted.start()
        wait_running(restarted)
        wait_query(restarted, observe_native=True)
        restarted.exec_run(("python3", "-c", "import os; os.kill(int(open('/var/lib/postgresql/data/postmaster.pid').readline()), 15)"))
        wait_exit(restarted, 1)
        require(PASSWORD.encode() not in restarted.logs(stdout=True, stderr=True), "password reached failure logs")
        restarted.remove()
        containers.remove(restarted)

        recovery = create(client, image.id, network.name, data.name, "recovery")
        containers.append(recovery)
        recovery.start()
        wait_running(recovery)
        wait_query(recovery, observe_native=True)
        recovery.kill(signal="KILL")
        wait_exit(recovery, 137)
        recovery.remove()
        containers.remove(recovery)

        recovered = create(client, image.id, network.name, data.name, "recovered")
        containers.append(recovered)
        recovered.start()
        wait_running(recovered)
        wait_query(recovered, observe_native=True)
        recovered.stop(timeout=10)
        wait_exit(recovered, 0)
        recovered.remove()
        containers.remove(recovered)

        refused = create(client, image.id, network.name,
                         str(HOST_RECORDS / "wrong-owner-data"), "wrong-owner")
        containers.append(refused)
        refused.start()
        wait_exit(refused, 1)
        require(PASSWORD.encode() not in refused.logs(stdout=True, stderr=True), "password reached refusal logs")
    finally:
        for container in reversed(containers):
            container.reload()
            require(container.labels.get("org.openj92.cpk.test-run") == RUN, "foreign container cleanup refused")
            container.remove(force=True)
        for volume in reversed(volumes):
            volume.reload()
            require(volume.attrs["Labels"].get("org.openj92.cpk.test-run") == RUN, "foreign volume cleanup refused")
            volume.remove(force=True)
        if network is not None:
            if controller_connected and controller is not None:
                network.disconnect(controller, force=True)
            network.reload()
            require(network.attrs["Labels"].get("org.openj92.cpk.test-run") == RUN, "foreign network cleanup refused")
            network.remove()


def main() -> int:
    client = docker.from_env()
    tag = f"control-plane-kit-postgres-source:{RUN}"
    image, owned = select_image(client, tag)
    try:
        exercise(client, image)
    finally:
        try:
            if not owned:
                cleanup_files()
        finally:
            cleanup_image(client, image, tag, owned)
    if not owned:
        print(json.dumps({"postgres_published_qualification": {
            "reference": os.environ["CPK_POSTGRES_IMAGE"],
            "source": os.environ["CPK_POSTGRES_SOURCE_REVISION"],
            "recipe_sha256": os.environ["CPK_POSTGRES_RECIPE_SHA256"],
            "image_id": image.id, "platform": "linux/amd64", "configured_user": "70:70",
            "qualification": "PASS", "owned_cleanup": "VERIFIED",
            "borrowed_image_removed": False,
        }}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
