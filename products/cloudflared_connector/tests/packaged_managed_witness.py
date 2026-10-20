"""Product-owned executable targets for the distinct managed image.

Invoked only by the owning Docker harness. The controlled stop case is not
evidence of real cloudflared management or shutdown.
"""
import base64
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


ENTRYPOINT = "control_plane_kit_servers_cloudflared_connector.entrypoint"
READER = "control_plane_kit_servers_cloudflared_connector.readiness"
OWNER = "org.openj92.cpk.test-run"
MAX_BYTES = 131072


class QualificationFailure(AssertionError):
    """Closed, fixture-owned reason code without candidate material."""


def require(condition, reason):
    if not condition:
        raise QualificationFailure(reason)


def image_contents():
    from importlib import metadata
    version = subprocess.run(["/usr/local/bin/cloudflared", "version"],
                             capture_output=True, timeout=3)
    require(version.returncode == 0 and b"2026.6.1" in version.stdout, "native_version")
    for name, commit in (
        ("control-plane-kit-core", "73d87e99bf711ff8a88112ca56c5eee8055ac5b7"),
        ("control-plane-kit-server-sdk", "1657cb91b143931bafcdb32108950d2bbbb66d95"),
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


def native_identity():
    """Observe the actual namespace, without emitting environment or tokens."""
    require(os.getuid() == 65532 and os.getgid() == 65532, "numeric_uid")
    command = Path("/proc/1/cmdline").read_bytes().split(b"\0")
    require(command[:3] == [b"python", b"-m", ENTRYPOINT.encode()], "python_pid1")
    children = []
    for directory in Path("/proc").iterdir():
        if not directory.name.isdecimal():
            continue
        try:
            executable = (directory / "exe").readlink()
            fields = (directory / "stat").read_text().rsplit(")", 1)[1].split()
        except FileNotFoundError:
            continue
        if str(executable) == "/usr/local/bin/cloudflared":
            require(int(fields[1]) == 1, "native_parent")
            require(int(fields[2]) == int(directory.name), "native_group")
            environment = (directory / "environ").read_bytes().split(b"\0")
            require([value for value in environment if value] ==
                    [b"TUNNEL_TOKEN_FILE=/run/secrets/cloudflared-token"], "native_environment")
            children.append([int(directory.name), int(fields[2]), fields[19]])
    require(len(children) == 1, "native_alive_interval_unproved")
    return children[0]


def management_observation():
    requests = json.loads(Path("/witness/requests.json").read_text())
    before = native_identity()
    for name, path, credential in (
        ("capabilities", "/__control/capabilities", requests["capabilities"]),
        ("liveness", "/__control/health/liveness", requests["liveness"]),
        ("readiness", "/__control/health/readiness", requests["readiness"]),
        ("denied", "/__control/health/readiness", None),
    ):
        connection = HTTPConnection("127.0.0.1", 8000, timeout=1)
        try:
            headers = {} if credential is None else {"Authorization": "Bearer " + credential}
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            body = response.read(MAX_BYTES + 1)
            require(len(body) <= MAX_BYTES, "response_bound")
            require(response.status == (401 if name == "denied" else 200), "management_status")
            if name in ("liveness", "readiness"):
                value = json.loads(body)
                require(value["request_id"] == "health-request", "health_correlation")
                expected = ("healthy",) if name == "liveness" else ("unhealthy", "unknown")
                require(value["outcome"] in expected, "health_truth")
        finally:
            connection.close()
    require(native_identity() == before, "native_changed_during_management")
    return before


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


def fresh_credential(value, *, static=False, kind=None):
    """Retain the existing fixture's grant, using a real short validity window."""
    import jwt
    import control_plane_kit_core as core
    from managed_control_fixtures import token
    original = token(value, static=static, kind=kind)
    payload = jwt.decode(original, options={"verify_signature": False})
    key = "workload_node_control_surface_read" if static else "workload_node_health_read"
    now = int(time.time()) - 1
    payload.update(iat=now, nbf=now, exp=now + 100)
    payload[key].update(issued_at=now, not_before=now, expires_at=now + 100)
    codec = (core.DelegatedWorkloadReceiverControlSurfaceReadGrantCodec() if static
             else core.DelegatedWorkloadReceiverHealthReadGrantCodec())
    codec.decode(payload[key])
    private = value.static_private if static else value.health_private
    return jwt.encode(payload, private, algorithm="EdDSA",
                      headers=jwt.get_unverified_header(original))


def prepare_files(records):
    import control_plane_kit_core as core
    from managed_control_fixtures import fixture
    value = fixture()
    files = {
        "control.json": core.ReceiverNodeControlConfigurationCodec().encode_bytes(value.config),
        "token": base64.b64encode(json.dumps({
            "a": "synthetic-account", "s": base64.b64encode(b"x" * 32).decode(),
            "t": str(uuid.uuid4()),
        }).encode()),
        "requests.json": json.dumps({
            "capabilities": fresh_credential(value, static=True),
            "liveness": fresh_credential(value, kind=core.NodeHealthReadKind.LIVENESS),
            "readiness": fresh_credential(value),
        }).encode(),
    }
    for name, content in files.items():
        path = records / name
        path.write_bytes(content)
        path.chmod(0o444 if name == "control.json" else 0o400)
        os.chown(path, 65532, 65532)


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
    require(not any(event.get("Action") in ("restart", "start") for event in events),
            "competing_start")
    return {"term_time_ns": first, "kill_time_ns": second, "die_time_ns": terminal}


def resolve_profile(client, container):
    container.reload()
    info, version = client.info(), client.version()
    config = container.attrs["Config"]
    require(info.get("OSType") == "linux", "stop_platform_unproved")
    require(config.get("StopSignal") == "SIGTERM", "stop_signal_unproved")
    timeout = config.get("StopTimeout")
    # Docker Info does not expose a DefaultStopTimeout field. Do not fabricate
    # one or infer an actual daemon default from generic Linux documentation.
    # The absent-timeout resolution path is explicitly outstanding for review.
    require(type(timeout) is int and timeout == 10, "stop_profile_unproved")
    return {"engine_id": info["ID"], "engine_version": version["Version"],
            "engine_commit": version.get("GitCommit"), "stop_timeout": timeout,
            "timeout_origin": "container", "stop_signal": config["StopSignal"]}


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
    import docker
    from control_plane_kit_interpreters.docker.sdk import DockerSdkClient
    records = Path("/witness")
    run = os.environ["CPK_MANAGED_TEST_RUN"]
    image_id = os.environ["CPK_MANAGED_IMAGE"]
    host_records = os.environ["CPK_MANAGED_HOST_RECORDS"]
    host_tests = os.environ["CPK_MANAGED_HOST_TESTS"]
    client = docker.from_env(timeout=5)
    owner = DockerSdkClient(client=client)
    created = []

    def create(name, **kwargs):
        require(not client.containers.list(all=True, filters={"name": "^/" + name + "$"}),
                "existing_container")
        container = client.containers.create(
            image_id, name=name, network_mode="none",
            labels={OWNER: run, "org.openj92.project": "control-plane-kit-servers"},
            **kwargs)
        created.append(container.id)
        (records / "containers.json").write_text(json.dumps(created))
        return container

    def execute(container, mode):
        result = container.exec_run(["python", "/witness-tests/packaged_managed_witness.py", mode])
        require(len(result.output) <= 4096, "helper_output_bound")
        require(result.exit_code == 0, "real_native_observation_failed")
        return json.loads(result.output)

    def wait_receipt(container, expected):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            container.reload()
            require(container.status == "running", "controlled_early_exit")
            output = container.logs(tail=3)
            require(len(output) <= 128, "controlled_log_bound")
            if expected in output.splitlines():
                return
            time.sleep(0.05)
        require(False, "controlled_receipt_timeout")

    try:
        image = client.images.get(image_id)
        verify_image(image)
        prepare_files(records)
        mounts = {
            host_tests: {"bind": "/witness-tests", "mode": "ro"},
            host_records + "/control.json": {"bind": "/etc/cpk/cloudflared/control.json", "mode": "ro"},
            host_records + "/token": {"bind": "/run/secrets/cloudflared-token", "mode": "ro"},
            host_records + "/requests.json": {"bind": "/witness/requests.json", "mode": "ro"},
            str(Path(host_tests).parent / "licenses/cloudflared-manifest.json"):
                {"bind": "/witness/notice-manifest.json", "mode": "ro"},
        }
        native = create(run + "-native", volumes=mounts, environment={
            "CPK_WRAPPER_CONFIGURATION_FILE": "/etc/cpk/cloudflared/control.json",
            "TUNNEL_TOKEN_FILE": "/run/secrets/cloudflared-token",
        })
        native.start()
        deadline = time.monotonic() + 15
        # No replacement launch. Every observation belongs to this one identity.
        before = execute(native, "identity")
        contents = execute(native, "contents")
        observed = None
        while time.monotonic() < deadline:
            observed = execute(native, "management")
            if not isinstance(observed, dict) or not observed.get("pending"):
                break
            require(observed["identity"] == before, "native_changed_during_startup")
            time.sleep(0.05)
        require(observed == before and time.monotonic() <= deadline, "native_interval")
        require(execute(native, "identity") == before, "native_changed_before_stop")
        profile = resolve_profile(client, native)
        owner.stop_container(native.id)
        native.reload()
        require(native.status == "exited", "native_stop_incomplete")
        require(native.attrs["State"]["ExitCode"] == 0, "native_stop_not_clean")

        controlled = create(
            run + "-profile", entrypoint=["python", "/witness-tests/packaged_managed_witness.py",
                                        "controlled"],
            volumes={host_tests: {"bind": "/witness-tests", "mode": "ro"}},
            healthcheck={"test": ["NONE"]})
        controlled.start()
        require(resolve_profile(client, controlled) == profile, "profile_mismatch")
        wait_receipt(controlled, b"handler-ready")
        wall_before, mono_before = time.time_ns(), time.monotonic_ns()
        owner.stop_container(controlled.id)
        wall_after, mono_after = time.time_ns(), time.monotonic_ns()
        require(abs((wall_after - wall_before) - (mono_after - mono_before)) <= 1_000_000_000,
                "controller_clock_discontinuity")
        controlled.reload()
        require(controlled.status == "exited" and controlled.attrs["State"]["ExitCode"] == 137,
                "controlled_terminal_state")
        output = controlled.logs(tail=3)
        require(len(output) <= 128 and output.splitlines() == [b"handler-ready", b"term-received"],
                "controlled_receipts")
        events = events_between(client, controlled.id, wall_before // 1_000_000_000,
                                wall_after // 1_000_000_000 + 1)
        evidence = verify_stop_events(events)
        fatal = create(
            run + "-fatal", entrypoint=["python", "/witness-tests/packaged_managed_witness.py",
                                      "fatal"],
            volumes={host_tests: {"bind": "/witness-tests", "mode": "ro"}},
            healthcheck={"test": ["NONE"]})
        fatal.start()
        fatal_deadline = time.monotonic() + 5
        child = None
        while time.monotonic() < fatal_deadline:
            output = fatal.logs(tail=1)
            require(len(output) <= 128, "fatal_receipt_bound")
            if output:
                child = json.loads(output)
                break
            time.sleep(0.05)
        require(child is not None and child["child_pid"] == child["child_group"] > 1,
                "fatal_child_group")
        fatal.kill(signal="SIGKILL")
        require(fatal.wait(timeout=5)["StatusCode"] == 137, "fatal_exit")
        fatal.reload()
        require(fatal.status == "exited" and fatal.attrs["State"]["Pid"] == 0,
                "fatal_namespace_still_running")
        # Linux PID-namespace init death terminates namespace members. This is
        # Docker's stopped namespace evidence, not a scan of all host processes.
        result = {"stage": "managed_cloudflared", "outcome": "pass",
                  "docker_sdk": docker.__version__, **profile, **evidence, **contents}
    except QualificationFailure as failure:
        states = []
        for identity in created:
            try:
                container = client.containers.get(identity)
                state = container.attrs["State"]
                states.append({"id": identity, "status": container.status,
                               "exit_code": state["ExitCode"], "pid": state["Pid"]})
            except Exception:
                states.append({"id": identity, "status": "observation_unavailable"})
        print(json.dumps({"stage": "managed_cloudflared", "outcome": "unqualified",
                          "reason": str(failure), "states": states}), flush=True)
        raise
    finally:
        cleanup_failed = False
        for identity in reversed(created):
            try:
                container = client.containers.get(identity)
                require(container.labels.get(OWNER) == run, "cleanup_ownership")
                container.remove(force=True)
                require(not client.containers.list(all=True, filters={"id": identity}),
                        "cleanup_incomplete")
            except Exception:
                cleanup_failed = True
        client.close()
        require(not cleanup_failed, "managed_cleanup_incomplete")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    try:
        mode = sys.argv[1]
        if mode == "identity":
            print(json.dumps(native_identity()))
        elif mode == "management":
            try:
                print(json.dumps(management_observation()))
            except ConnectionRefusedError:
                print(json.dumps({"pending": True, "identity": native_identity()}))
        elif mode == "contents":
            print(json.dumps(image_contents()))
        elif mode == "controlled":
            controlled_process()
        elif mode == "fatal":
            fatal_process()
        elif mode == "controller":
            controller()
        else:
            raise QualificationFailure("invalid_witness_mode")
    except QualificationFailure as failure:
        print(str(failure), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        # Do not serialize Docker exception payloads, credentials or responses.
        print("managed cloudflared witness did not qualify", file=sys.stderr)
        raise SystemExit(1)
