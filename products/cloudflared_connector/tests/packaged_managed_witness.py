"""Product-owned executable targets for the distinct managed image.

Invoked only by the owning Docker harness. Image inspection and controlled
process cases do not prove real cloudflared management or shutdown. Mandatory
live qualification is owned by the later approved CPK/Cloudflare lane.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import uuid


ENTRYPOINT = "control_plane_kit_servers_cloudflared_connector.entrypoint"
READER = "control_plane_kit_servers_cloudflared_connector.readiness"
OWNER = "org.openj92.cpk.test-run"
OBSERVATION_MODES = frozenset(("contents",))
HELPER_REASONS = frozenset((
    "native_version", "installed_source_coordinate", "notice_source", "notice_path",
    "notice_blob", "dependency_license_metadata", "numeric_uid",
    "helper_output_bound", "helper_output_path", "helper_output_write",
    "helper_exception",
))
CONTROLLER_PHASES = frozenset(("setup", "artifact", "profile", "fatal", "cleanup"))
CONTROLLER_OPERATIONS = frozenset((
    "initialize", "inputs", "connect", "owner", "image_inspect", "prepare_files",
    "absence_check", "create", "record", "start", "reload",
    "result_read", "resolve_profile",
    "stop", "logs", "events", "kill", "wait", "remove", "close", "report",
))


class QualificationFailure(AssertionError):
    """Closed, fixture-owned reason code without candidate material."""


def require(condition, reason):
    if not condition:
        raise QualificationFailure(reason)


def mark_controller(context, phase, operation, helper_mode=None):
    require(phase in CONTROLLER_PHASES and operation in CONTROLLER_OPERATIONS
            and (helper_mode is None or helper_mode in OBSERVATION_MODES),
            "controller_context")
    context.update(phase=phase, operation=operation, helper_mode=helper_mode)


def emit_controller_failure(role, context):
    """Publish only closed marker values; emission cannot replace the failure."""
    try:
        if (role not in ("primary", "cleanup")
                or set(context) != {"phase", "operation", "helper_mode"}
                or context["phase"] not in CONTROLLER_PHASES
                or context["operation"] not in CONTROLLER_OPERATIONS
                or (context["helper_mode"] is not None
                    and context["helper_mode"] not in OBSERVATION_MODES)):
            return False
        print(json.dumps({"stage": "managed_cloudflared_controller_failure",
                          "outcome": "unqualified", "role": role, **context}), flush=True)
    except Exception:
        return False
    return True


def capture_controller_failure(role, context):
    snapshot = dict(context)
    return snapshot, emit_controller_failure(role, snapshot)


def emit_qualification_failure(failure, states):
    try:
        print(json.dumps({"stage": "managed_cloudflared_controller",
                          "outcome": "unqualified", "reason": str(failure),
                          "states": states}), flush=True)
    except Exception:
        return False
    return True


def finish_controller(primary_failure, cleanup_failed):
    if primary_failure is not None:
        raise primary_failure
    require(not cleanup_failed, "managed_cleanup_incomplete")


def helper_failure_value(failure):
    reason = (failure.args[0]
              if isinstance(failure, QualificationFailure) and len(failure.args) == 1
              else None)
    if type(reason) is not str or reason not in HELPER_REASONS:
        reason = "helper_exception"
    return {"outcome": "failure", "reason": reason}


def retain_helper_failure(mode, failure):
    if mode not in OBSERVATION_MODES:
        return False
    try:
        emit_helper(helper_failure_value(failure))
    except Exception:
        # A failed receipt cannot recover the original terminal helper failure.
        return False
    return True


def read_helper_result(local_path, deadline):
    require(time.monotonic() < deadline, "helper_deadline")
    descriptor = os.open(local_path, os.O_RDONLY | os.O_NOFOLLOW |
                         os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and stat.S_IMODE(before.st_mode) == 0o400
                and before.st_uid == 65532 and 0 < before.st_size <= 4096,
                "helper_result_file")
        value = os.read(descriptor, 4097)
        after = os.fstat(descriptor)
        require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and len(value) == before.st_size, "helper_result_changed")
    finally:
        os.close(descriptor)
    require(time.monotonic() < deadline, "helper_deadline")
    require(len(value) <= 4096, "helper_output_bound")
    decoded = json.loads(value)
    local_path.unlink()
    require(time.monotonic() < deadline, "helper_deadline")
    return decoded


def completed_helper(mode, exit_code, local_path, deadline):
    require(mode in OBSERVATION_MODES and type(exit_code) is int, "helper_completion")
    if exit_code == 0:
        value = read_helper_result(local_path, deadline)
        require(not (isinstance(value, dict) and value.get("outcome") == "failure"),
                "helper_failure_with_zero_exit")
        return value
    diagnostic = {"stage": "managed_cloudflared_helper", "mode": mode,
                  "exit_code": exit_code, "result": "invalid"}
    try:
        value = read_helper_result(local_path, deadline)
        if (type(value) is dict and set(value) == {"outcome", "reason"}
                and value["outcome"] == "failure" and type(value["reason"]) is str
                and value["reason"] in HELPER_REASONS):
            diagnostic.update(result="valid_error", reason=value["reason"])
    except FileNotFoundError:
        diagnostic["result"] = "unavailable"
    except Exception:
        # Never serialize exception details or replace the original inspection failure.
        diagnostic["result"] = "invalid"
    if time.monotonic() >= deadline:
        diagnostic = {"stage": "managed_cloudflared_helper", "mode": mode,
                      "exit_code": exit_code, "result": "deadline_exhausted"}
    print(json.dumps(diagnostic), flush=True)
    require(False, "package_inspection_failed")


def image_contents():
    require(os.getuid() == 65532 and os.getgid() == 65532, "numeric_uid")
    from importlib import metadata
    version = subprocess.run(["/usr/local/bin/cloudflared", "version"],
                             capture_output=True, timeout=3)
    require(version.returncode == 0 and b"2026.6.1" in version.stdout, "native_version")
    for name, commit in (
        ("control-plane-kit-core", "7afef43f3d3b981094e37dcb3062b6e3a4f3d674"),
        ("control-plane-kit-server-sdk", "220f63169e4bac79653937e97727406255279f7b"),
    ):
        direct = json.loads(metadata.distribution(name).read_text("direct_url.json"))
        require(commit in direct["url"], "installed_source_coordinate")
    manifest = json.loads(Path("/witness/notice-manifest.json").read_text())
    require(manifest["source_commit"] == "81a53555aa827fca88605d7e67ad5c03cda468d2",
            "notice_source")
    root = Path("/usr/share/licenses/cloudflared")
    for item in manifest["notices"]:
        path = Path(item["path"])
        require(not path.is_absolute() and ".." not in path.parts, "notice_path")
        content = (root / path).read_bytes()
        digest = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        require(digest == item["sha"], "notice_blob")
    for name in ("PyJWT", "cryptography"):
        distribution = metadata.distribution(name)
        require(any("license" in str(path).lower() and distribution.locate_file(path).is_file()
                    for path in distribution.files), "dependency_license_metadata")
    return {"native_version": "2026.6.1", "installed": {
        distribution.metadata["Name"]: distribution.version
        for distribution in metadata.distributions()}}


def controlled_process():
    def on_term(_signum, _frame):
        os.write(1, b"term-received\n")
    signal.signal(signal.SIGTERM, on_term)
    os.write(1, b"handler-ready\n")
    while True:
        time.sleep(1)


def fatal_process():
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
    print(json.dumps({"child_pid": child.pid, "child_group": os.getpgid(child.pid)}), flush=True)
    while True:
        time.sleep(1)


def events_between(client, identity, since, until):
    """Finite historical event query, never an open-ended listener."""
    stream = client.events(since=since, until=until,
                           filters={"container": identity}, decode=False)
    events, size = [], 0
    try:
        for raw in stream:
            size += len(raw)
            require(size <= 65536 and len(events) < 32, "event_bound")
            value = json.loads(raw)
            require(value.get("Actor", {}).get("ID") == identity, "event_identity")
            require(type(value.get("timeNano")) is int, "event_precision")
            events.append(value)
    finally:
        stream.close()
    return events


def verify_stop_events(events):
    kills = [event for event in events if event.get("Action") == "kill"]
    dies = [event for event in events if event.get("Action") == "die"]
    require(len(kills) == 2 and len(dies) == 1, "stop_sequence_unproved")
    require([event["Actor"]["Attributes"].get("signal") for event in kills] ==
            ["15", "9"], "stop_signal_sequence")
    require(dies[0]["Actor"]["Attributes"].get("exitCode") == "137", "stop_exit")
    first, second, terminal = kills[0]["timeNano"], kills[1]["timeNano"], dies[0]["timeNano"]
    require(first < second <= terminal, "event_clock_order")
    require(9_000_000_000 <= second - first <= 11_000_000_000, "stop_conformance")
    require(not any(event.get("Action") == "restart" or
                    (event.get("Action") == "start" and event["timeNano"] >= first)
                    for event in events),
            "competing_start")
    return {"term_time_ns": first, "kill_time_ns": second, "die_time_ns": terminal}


def resolve_profile(client, container):
    import docker
    container.reload()
    info, version = client.info(), client.version()
    config = container.attrs["Config"]
    print(json.dumps({
        "stage": "stop_profile_inputs", "container_id": container.id,
        "engine_id": info.get("ID"), "engine_version": version.get("Version"),
        "engine_commit": version.get("GitCommit"), "platform": info.get("OSType"),
        "docker_sdk": docker.__version__, "configured_signal": config.get("StopSignal"),
        "configured_timeout": config.get("StopTimeout"),
    }), flush=True)
    require(docker.__version__ == "7.2.0", "sdk_stop_semantics_unproved")
    require(info.get("OSType") == "linux", "stop_platform_unproved")
    require(config.get("StopSignal") == "SIGTERM", "stop_signal_unproved")
    timeout = config.get("StopTimeout")
    origin = "container"
    # These reviewed source identities have a fixed Unix default, not a
    # configurable daemon default. Unknown version/build pairs remain unproved.
    commit = version.get("GitCommit")
    engine_version = version.get("Version")
    fixed_source = {
        "28.5.1": "f8215cc266744ef195a50a70d427c345da2acdbb",
        "28.0.4": "6430e49a55babd9b8f4d08e70ecb2b68900770fe",
    }.get(engine_version) if type(engine_version) is str else None
    if (timeout is None and fixed_source is not None
            and type(commit) is str and 7 <= len(commit) <= 40
            and fixed_source.startswith(commit)):
        timeout, origin = 10, "engine_fixed_default"
    require(type(timeout) is int and timeout == 10, "stop_profile_unproved")
    return {"engine_id": info["ID"], "engine_version": version["Version"],
            "engine_commit": version.get("GitCommit"), "stop_timeout": timeout,
            "configured_stop_timeout": config.get("StopTimeout"),
            "reviewed_engine_source": fixed_source if origin == "engine_fixed_default" else None,
            "timeout_origin": origin, "stop_signal": config["StopSignal"]}


def verify_image(image):
    config = image.attrs["Config"]
    require(config["User"] == "65532:65532", "image_user")
    require(config["Entrypoint"] == ["python", "-m", ENTRYPOINT], "image_entrypoint")
    require(not config.get("Cmd"), "image_command")
    require(config.get("StopSignal") == "SIGTERM", "image_stop_signal")
    health = config["Healthcheck"]
    require(health["Test"] == ["CMD", "python", "-m", READER], "image_health_command")
    require((health["Interval"], health["Timeout"], health["Retries"]) ==
            (5_000_000_000, 3_000_000_000, 1), "image_health_bounds")


def controller():
    context = {"phase": "setup", "operation": "initialize", "helper_mode": None}
    primary_failure = None
    primary_context = None
    primary_reported = False
    cleanup_context = None
    client = None
    created = []

    def create(name, *, deadline=None, **kwargs):
        phase = context["phase"]
        mode = context["helper_mode"]
        if deadline is not None:
            require(time.monotonic() < deadline, "helper_deadline")
        mark_controller(context, phase, "absence_check", mode)
        require(not client.containers.list(all=True, filters={"name": "^/" + name + "$"}),
                "existing_container")
        if deadline is not None:
            require(time.monotonic() < deadline, "helper_deadline")
        mark_controller(context, phase, "create", mode)
        container = client.containers.create(
            image_id, name=name, network_mode="none",
            labels={OWNER: run, "org.openj92.project": "control-plane-kit-servers"},
            **kwargs)
        created.append(container.id)
        mark_controller(context, phase, "record", mode)
        (records / "containers.json").write_text(json.dumps(created))
        if deadline is not None:
            require(time.monotonic() < deadline, "helper_deadline")
        return container

    def wait_receipt(container, expected):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            mark_controller(context, "profile", "reload")
            container.reload()
            require(container.status == "running", "controlled_early_exit")
            mark_controller(context, "profile", "logs")
            output = container.logs(tail=3)
            require(len(output) <= 128, "controlled_log_bound")
            if expected in output.splitlines():
                return
            time.sleep(0.05)
        require(False, "controlled_receipt_timeout")

    try:
        import docker
        from control_plane_kit_interpreters.docker.sdk import DockerSdkClient
        mark_controller(context, "setup", "inputs")
        records = Path("/witness")
        results = records / "results"
        run = os.environ["CPK_MANAGED_TEST_RUN"]
        image_id = os.environ["CPK_MANAGED_IMAGE"]
        host_records = os.environ["CPK_MANAGED_HOST_RECORDS"]
        host_tests = os.environ["CPK_MANAGED_HOST_TESTS"]
        mark_controller(context, "setup", "connect")
        client = docker.from_env(timeout=5)
        mark_controller(context, "setup", "owner")
        owner = DockerSdkClient(client=client)
        mark_controller(context, "setup", "image_inspect")
        image = client.images.get(image_id)
        verify_image(image)
        mark_controller(context, "setup", "prepare_files")
        results.mkdir(mode=0o770)
        results.chmod(0o770)
        # The host run owner can clean up failed observations; the numeric
        # product group can write only this fixture directory.
        os.chown(results, records.stat().st_uid, 65532)
        mounts = {
            host_tests: {"bind": "/witness-tests", "mode": "ro"},
            host_records + "/results": {"bind": "/witness-results", "mode": "rw"},
            str(Path(host_tests).parent / "licenses/cloudflared-manifest.json"):
                {"bind": "/witness/notice-manifest.json", "mode": "ro"},
        }
        name = "cpk-witness-" + uuid.uuid4().hex + ".json"
        deadline = time.monotonic() + 15
        old_timeout = client.api.timeout
        client.api.timeout = 1
        try:
            mark_controller(context, "artifact", "create", "contents")
            inspection = create(
                run + "-contents", deadline=deadline,
                entrypoint=["python", "/witness-tests/packaged_managed_witness.py",
                            "contents", "/witness-results/" + name],
                volumes=mounts, healthcheck={"test": ["NONE"]})
            require(time.monotonic() < deadline, "helper_deadline")
            mark_controller(context, "artifact", "start", "contents")
            inspection.start()
            require(time.monotonic() < deadline, "helper_deadline")
            while True:
                require(time.monotonic() < deadline, "helper_deadline")
                mark_controller(context, "artifact", "reload", "contents")
                inspection.reload()
                require(time.monotonic() < deadline, "helper_deadline")
                state = inspection.attrs["State"]
                if state["Status"] == "exited":
                    require(type(state["ExitCode"]) is int, "helper_completion")
                    break
                require(state["Status"] in ("created", "running"),
                        "package_inspection_state")
                time.sleep(0.05)
            mark_controller(context, "artifact", "result_read", "contents")
            contents = completed_helper("contents", state["ExitCode"], results / name, deadline)
        finally:
            client.api.timeout = old_timeout

        mark_controller(context, "profile", "create")
        controlled = create(
            run + "-profile", entrypoint=["python", "/witness-tests/packaged_managed_witness.py",
                                        "controlled"],
            volumes={host_tests: {"bind": "/witness-tests", "mode": "ro"}},
            healthcheck={"test": ["NONE"]})
        mark_controller(context, "profile", "start")
        controlled.start()
        mark_controller(context, "profile", "resolve_profile")
        profile = resolve_profile(client, controlled)
        wait_receipt(controlled, b"handler-ready")
        wall_before, mono_before = time.time_ns(), time.monotonic_ns()
        mark_controller(context, "profile", "stop")
        owner.stop_container(controlled.id)
        wall_after, mono_after = time.time_ns(), time.monotonic_ns()
        require(abs((wall_after - wall_before) - (mono_after - mono_before)) <= 1_000_000_000,
                "controller_clock_discontinuity")
        mark_controller(context, "profile", "reload")
        controlled.reload()
        require(controlled.status == "exited" and controlled.attrs["State"]["ExitCode"] == 137,
                "controlled_terminal_state")
        mark_controller(context, "profile", "logs")
        output = controlled.logs(tail=3)
        require(len(output) <= 128 and output.splitlines() == [b"handler-ready", b"term-received"],
                "controlled_receipts")
        mark_controller(context, "profile", "events")
        events = events_between(client, controlled.id, wall_before // 1_000_000_000,
                                wall_after // 1_000_000_000 + 1)
        evidence = verify_stop_events(events)
        mark_controller(context, "fatal", "create")
        fatal = create(
            run + "-fatal", entrypoint=["python", "/witness-tests/packaged_managed_witness.py",
                                      "fatal"],
            volumes={host_tests: {"bind": "/witness-tests", "mode": "ro"}},
            healthcheck={"test": ["NONE"]})
        mark_controller(context, "fatal", "start")
        fatal.start()
        fatal_deadline = time.monotonic() + 5
        child = None
        while time.monotonic() < fatal_deadline:
            mark_controller(context, "fatal", "logs")
            output = fatal.logs(tail=1)
            require(len(output) <= 128, "fatal_receipt_bound")
            if output:
                child = json.loads(output)
                break
            time.sleep(0.05)
        require(child is not None and child["child_pid"] == child["child_group"] > 1,
                "fatal_child_group")
        mark_controller(context, "fatal", "kill")
        fatal.kill(signal="SIGKILL")
        mark_controller(context, "fatal", "wait")
        require(fatal.wait(timeout=5)["StatusCode"] == 137, "fatal_exit")
        mark_controller(context, "fatal", "reload")
        fatal.reload()
        require(fatal.status == "exited" and fatal.attrs["State"]["Pid"] == 0,
                "fatal_namespace_still_running")
        # Linux PID-namespace init death terminates namespace members. This is
        # Docker's stopped namespace evidence, not a scan of all host processes.
        result = {"stage": "managed_cloudflared_controller", "outcome": "package_pass",
                  "live_qualification": "pending",
                  "profile_container_id": controlled.id,
                  "docker_sdk": docker.__version__, **profile, **evidence, **contents}
    except Exception as failure:
        primary_failure = failure
        primary_context, primary_reported = capture_controller_failure("primary", context)
        if isinstance(failure, QualificationFailure):
            states = []
            for identity in created:
                try:
                    container = client.containers.get(identity)
                    state = container.attrs["State"]
                    states.append({"id": identity, "status": container.status,
                                   "exit_code": state["ExitCode"], "pid": state["Pid"]})
                except Exception:
                    states.append({"id": identity, "status": "observation_unavailable"})
            mark_controller(context, context["phase"], "report")
            emit_qualification_failure(failure, states)
    finally:
        for identity in reversed(created):
            try:
                mark_controller(context, "cleanup", "reload")
                container = client.containers.get(identity)
                require(container.labels.get(OWNER) == run, "cleanup_ownership")
                mark_controller(context, "cleanup", "remove")
                container.remove(force=True)
                mark_controller(context, "cleanup", "absence_check")
                require(not client.containers.list(all=True, filters={"id": identity}),
                        "cleanup_incomplete")
            except Exception:
                if cleanup_context is None:
                    cleanup_context = dict(context)
        if client is not None:
            try:
                mark_controller(context, "cleanup", "close")
                client.close()
            except Exception:
                if cleanup_context is None:
                    cleanup_context = dict(context)
        if cleanup_context is not None:
            emit_controller_failure("cleanup", cleanup_context)
    if primary_context is not None and not primary_reported:
        emit_controller_failure("primary", primary_context)
    finish_controller(primary_failure, cleanup_context is not None)
    mark_controller(context, "cleanup", "report")
    try:
        print(json.dumps(result), flush=True)
    except Exception:
        emit_controller_failure("primary", context)
        raise


def emit_helper(value):
    content = json.dumps(value).encode()
    require(len(content) <= 4096, "helper_output_bound")
    path = sys.argv[2]
    require(path.startswith("/witness-results/cpk-witness-")
            and "/" not in path[len("/witness-results/"):],
            "helper_output_path")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        require(os.write(descriptor, content) == len(content), "helper_output_write")
        os.fchmod(descriptor, 0o400)
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    mode = None
    try:
        mode = sys.argv[1]
        if mode == "contents":
            emit_helper(image_contents())
        elif mode == "controlled":
            controlled_process()
        elif mode == "fatal":
            fatal_process()
        elif mode == "controller":
            controller()
        else:
            raise QualificationFailure("invalid_witness_mode")
    except QualificationFailure as failure:
        retain_helper_failure(mode, failure)
        print(str(failure), file=sys.stderr)
        raise SystemExit(1)
    except Exception as failure:
        retain_helper_failure(mode, failure)
        # Do not serialize Docker exception payloads, credentials or responses.
        print("managed cloudflared witness did not qualify", file=sys.stderr)
        raise SystemExit(1)
