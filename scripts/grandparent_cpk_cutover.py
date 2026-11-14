"""Issue #399's fixed root-process maintenance proposal; no general updater.

Invoke only in the reviewed Docker-backed installer after exact action approval.
The provider seam exists for finite source tests, not an alternative interpreter.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import signal
import socket
import stat
import struct
import subprocess
import sys
import time

ENGINE = "d23d00aa-b281-448d-bc95-c8e47efeeea2"
OLD = "3584eabe7b2c1c278ea9053f9ac73a16acc85d086c641058f5430549fd887e0f"
OLD_IMAGE = "sha256:62e4ee7fe4e8326b762c36306c3a810a15d684cb9d2c22515ac2f092296d2e50"
IMAGE = "sha256:49ae1044c73f5fb94cce229f736be5fa1ee3d1a0fcbe4e423d54b2831d2986a7"
NETWORK = "6af12defe4940ef19218de1f01ff94f4777c5d00832d8eac8c7e93aac4362f7f"
NODE = "cpk163-gparent-20261109-cpk"
NAME = "cpk-cpk163-gparent-20261109-cpk163-gparent-20261109-" + NODE
BACKUP = NAME + "-before-mcp399-20261114-01"
RUN = "cpk399-gparent-mcp-switch-20261114-01"
PROFILE = "grandparent-read-only-v1"
COMMAND = ["python", "-m", "control_plane_kit_servers_cpk_server.server"]
LABELS = {"org.openj92.cpk.installation": "cpk163-gparent-20261109",
          "org.openj92.cpk.acquisition": "7051ebe49a173e63f768bcd99edc98e8",
          "org.openj92.cpk.bootstrap": "ce965390406112dbfd0ad71de4fc41e56ec43d4751c509d271dfb7d6cd9c590b"}
WORKSPACE = "cpk163-child-20261109"
DRAFT = "000f2e90-ece8-4584-8425-89fecb0b98a5"
DESIRED = "773b4491-06ac-494f-abf5-5f1c199c66bc"
CURRENT = "17c48b45-feb4-43ca-85e6-3e0a662a00aa"
PREFIX = "cpk-cpk163-gparent-20261109-cpk163-gparent-20261109-" + NODE
MOUNTS = {
    PREFIX + "-file-24e6016f6736c00b": "/run/secrets/cpk-installation/provider-client",
    PREFIX + "-workspace-authority": "/etc/cpk/cpk-server/workspace-authority.json",
    PREFIX + "-configuration-3b93d8ead8e9edb1": "/etc/cpk/cpk-server/control.json",
    PREFIX + "-configuration-789bb7d30a241287": "/etc/cpk/cpk-server/managed-health.json",
    PREFIX + "-configuration-dc47a145e4e2de81": "/etc/cpk/cpk-server/managed-verification.json"}
PORTS = {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18163"}]}
PUBLIC_PLAN_SHA = "c451d7cffad919297c3a669db6ca920271d3038526b2a8248cd8201ce7a41279"


class Hold(Exception):
    """Closed failure without provider/private payload."""


class ChildOutcomeError(Hold):
    def __init__(self, outcomes):
        super().__init__("owned-child-outcome-unverified")
        self.outcomes = outcomes


def require(value, code):
    if not value:
        raise Hold(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def environment(config):
    pairs = [entry.split("=", 1) for entry in config["Env"]]
    require(all(len(pair) == 2 for pair in pairs), "environment-shape")
    require(len({pair[0] for pair in pairs}) == len(pairs), "environment-shape")
    return dict(pairs)


def configured_mounts(host):
    mounts = host["Mounts"]
    require(len(mounts) == 6 and not host.get("Binds") and not host.get("VolumesFrom"), "mounts")
    seen = {}
    for mount in mounts:
        require(set(mount) <= {"Type", "Source", "Target", "ReadOnly", "VolumeOptions",
                               "Consistency", "BindOptions"}, "mounts")
        require(not mount.get("Consistency") and not mount.get("BindOptions"), "mounts")
        if mount["Type"] == "volume":
            require(MOUNTS.get(mount["Source"]) == mount["Target"] and mount.get("ReadOnly") is True,
                    "mounts")
            require(mount.get("VolumeOptions") == {"Subpath": "content"}, "mounts")
        else:
            require(mount["Type"] == "bind" and mount["Source"] == mount["Target"] == "/var/run/docker.sock"
                    and mount.get("ReadOnly", False) is False, "mounts")
        require(mount["Target"] not in seen, "mounts")
        seen[mount["Target"]] = mount
    require(set(seen) == set(MOUNTS.values()) | {"/var/run/docker.sock"}, "mounts")


def actual_mounts(value):
    seen = set()
    require(len(value["Mounts"]) == 6, "actual-mounts")
    for mount in value["Mounts"]:
        require(mount["Destination"] not in seen, "actual-mounts")
        seen.add(mount["Destination"])
        if mount["Type"] == "volume":
            require(MOUNTS.get(mount["Name"]) == mount["Destination"] and mount["RW"] is False,
                    "actual-mounts")
        else:
            require(mount["Type"] == "bind" and mount["Source"] == mount["Destination"] ==
                    "/var/run/docker.sock" and mount["RW"] is True, "actual-mounts")


HOST_FIELDS = ("NetworkMode", "PortBindings", "Mounts", "GroupAdd", "LogConfig", "RestartPolicy",
               "ReadonlyRootfs", "CapAdd", "CapDrop", "SecurityOpt", "Memory", "NanoCpus", "PidsLimit",
               "AutoRemove", "Privileged", "PublishAllPorts")
DEFAULT_HOST = {"Runtime": "runc", "IpcMode": "private", "CgroupnsMode": "private",
                "ShmSize": 67108864, "ConsoleSize": [0, 0]}
# Docker's ordinary Linux defaults; they are preserved, never relaxed.
DEFAULT_HOST["MaskedPaths"] = ["/proc/acpi", "/proc/asound", "/proc/interrupts", "/proc/kcore",
    "/proc/keys", "/proc/latency_stats", "/proc/sched_debug", "/proc/scsi", "/proc/timer_list",
    "/proc/timer_stats", "/sys/devices/virtual/powercap", "/sys/firmware"]
DEFAULT_HOST["ReadonlyPaths"] = ["/proc/bus", "/proc/fs", "/proc/irq", "/proc/sys", "/proc/sysrq-trigger"]


def host_contract(host, socket_gid):
    configured_mounts(host)
    require(host["NetworkMode"] == NETWORK and host["PortBindings"] == PORTS, "network-or-ports")
    require(host["GroupAdd"] == [str(socket_gid)], "socket-group")
    require(host["LogConfig"] == {"Type": "json-file", "Config": {"max-size": "1m", "max-file": "2"}}, "logging")
    require(host["RestartPolicy"] == {"Name": "no", "MaximumRetryCount": 0}, "restart-policy")
    for key in ("ReadonlyRootfs", "CapAdd", "CapDrop", "SecurityOpt", "Memory", "NanoCpus", "PidsLimit",
                "AutoRemove", "Privileged", "PublishAllPorts"):
        require(host.get(key) in (None, False, 0, []), "host-options")
    for key, value in host.items():
        if key in HOST_FIELDS:
            continue
        if key in DEFAULT_HOST:
            require(value == DEFAULT_HOST[key], "host-options")
        else:
            require(value in (None, False, 0, "", [], {}), "host-options")


def process_contract(config):
    require(config["User"] == "10001" and config["Cmd"] == COMMAND and
            config.get("Entrypoint") in (None, []) and config["WorkingDir"] == "/app", "process-config")
    require(not config.get("Tty") and not config.get("OpenStdin") and not config.get("NetworkDisabled")
            and not config.get("Healthcheck") and not config.get("OnBuild"), "process-config")
    require(config.get("StopSignal", "SIGTERM") == "SIGTERM", "process-config")


class Journal:
    """One attempt's closed receipt; no retry/resume or product-state ownership."""

    def __init__(self, root, approval, owner=None):
        self.root = root
        self.owner = owner
        self.child_outcomes = []
        self.write("init", {})
        self.approval = approval
        self.new_id = None
        self.pending = None
        self.stage = "preflight"
        self.started = False
        self.original_state = "not-observed"
        self.original_retained = False

    def write(self, operation, value):
        if self.owner is None:
            write_evidence(self.root, operation, value)
        else:
            require(self.owner == (501, 20), "evidence-owner")
            try:
                result = run_as_owner([sys.executable, __file__, "--write-evidence", operation, str(self.root)], canonical(value))
            except ChildOutcomeError as error:
                self.child_outcomes.extend(error.outcomes)
                raise
            require(result.returncode == 0 and result.stdout == b"recorded\n", "evidence-write")

    def event(self, kind, **updates):
        value = dict(event=kind, stage=self.stage, successor_id=self.new_id,
                     pending=self.pending, original_state=self.original_state)
        value.update(updates)
        self.write("event", value)

    def effect(self, stage, call):
        self.stage = self.pending = stage
        self.event("dispatch-intent")
        value = call()
        self.pending = None
        self.event("returned")
        return value

    def create(self, call):
        self.stage = self.pending = "create-successor"
        self.event("dispatch-intent")
        created = call()
        require(type(created) is dict and re.fullmatch(r"[0-9a-f]{64}", created.get("Id", "")),
                "create-outcome-unknown")
        self.new_id = created["Id"]
        # ID and completed dispatch are one durable event. If persistence fails,
        # the prior durable pending intent remains authoritative; never replay.
        self.event("created-id-confirmed", pending=None)
        self.pending = None
        return self.new_id

    def outcome(self, success, code):
        # Failure remains bounded even if the provider exception contains secrets.
        return dict(schema="cpk399.maintenance.v1", run=RUN, owner="North",
            approval_reference=self.approval, original_id=OLD, successor_id=self.new_id,
            stage=self.stage, status="verified" if success else "HOLD", reason=code,
            pending=self.pending, retry=False, rollback=False,
            startup_attempted=self.started, schema_change_possible=self.started,
            original_state=self.original_state,
            original_stopped_retained=(self.original_retained if self.original_state == "stopped-observed"
                                       else None if self.original_state == "stop-outcome-unknown" else False),
            saved_revision_compared=success, client_connected=False,
            child_outcomes=list(self.child_outcomes),
            historical_inspector=("original-id-stopped-by-maintenance" if self.original_state == "stopped-observed"
                else "original-stop-unverified" if self.original_state == "stop-outcome-unknown" else "not-superseded"))

    def finish(self, success, code):
        result = self.outcome(success, code)
        self.write("finish", result)
        return result


def write_evidence(root, operation, value):
    require(operation in ("init", "event", "finish") and root.is_absolute(), "evidence-operation")
    if operation == "init":
        root.mkdir(mode=0o700, exist_ok=False)
    metadata = root.lstat()
    require(stat.S_ISDIR(metadata.st_mode) and not root.is_symlink() and metadata.st_uid == os.getuid()
            and stat.S_IMODE(metadata.st_mode) == 0o700, "evidence-directory")
    name = "receipt.json" if operation == "finish" else "events.jsonl"
    flags = os.O_WRONLY | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if operation in ("init", "finish") else os.O_APPEND)
    descriptor = os.open(root / name, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600, "evidence-file")
        data = b"" if operation == "init" else canonical(value) + b"\n"
        require(len(data) <= 8192, "evidence-bound")
        while data:
            count = os.write(descriptor, data)
            require(count > 0, "evidence-write")
            data = data[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class VerifiedProfile:
    """Only the already owner-read, verified bytes for this bounded read batch."""

    def __init__(self, profile, credential):
        self.endpoint = profile.endpoint
        self.__credential = credential

    def credential(self, role):
        require(role == "operator", "verification-role")
        return self.__credential


class SavedReads:
    """Actual selected public client under its credential owner's UID."""

    def __init__(self, credential_path):
        metadata = credential_path.lstat()
        require(stat.S_ISREG(metadata.st_mode) and not credential_path.is_symlink()
                and metadata.st_uid == 501 and stat.S_IMODE(metadata.st_mode) == 0o400
                and metadata.st_size == 64, "credential-metadata")
        self.path = credential_path

    def owner_credential(self):
        from control_plane_kit_servers_cpk_server.client.profile import ClientProfile
        self.owner_profile = ClientProfile("http://127.0.0.1:18163", WORKSPACE,
            {"operator": self.path, "approver": Path("/not-provided"), "worker": Path("/not-provided")},
            Path("/not-used"))
        return self.owner_profile.credential("operator")

    def accept_verified(self, credential):
        self.profile = VerifiedProfile(self.owner_profile, credential)

    def read(self, suffix):
        # Existing public transport owns redirects, bounded decoding and safe errors.
        from control_plane_kit_servers_cpk_server.client.transport import PublicHttpTransport
        transport = PublicHttpTransport(self.profile, timeout_seconds=5)
        route = {"workspace": "read.workspace", "desired": "read.desired-graph",
                 "revision": "read.desired-topology-draft-revision",
                 "attempts": "read.desired-topology-draft-revision-attempts"}[suffix]
        coordinates = dict(workspace_id=WORKSPACE)
        if suffix in ("revision", "attempts"):
            coordinates.update(draft_id=DRAFT, revision="1")
        return transport.call(route, path_parameters=coordinates,
            payload={"limit": 50} if suffix == "attempts" else {}, credential_role="operator")

    def saved(self):
        workspace, desired, revision, attempts = (self.read(k) for k in ("workspace", "desired", "revision", "attempts"))
        require(workspace["workspace"]["workspace_id"] == WORKSPACE and
                workspace["workspace"]["current_graph_id"] == CURRENT and
                workspace["workspace"]["desired_graph_id"] == DESIRED and
                workspace["workspace"]["desired_graph_revision"] == 1, "saved-workspace-mismatch")
        require(revision["workspace_id"] == WORKSPACE and revision["draft_id"] == DRAFT and
                revision["revision"] == 1 and revision["graph_id"] == DESIRED and
                isinstance(revision["graph_descriptor"], str), "saved-revision-mismatch")
        require(desired["assigned"] is True and desired["graph_id"] == DESIRED and
                type(attempts["items"]) is list and len(attempts["items"]) <= 50, "saved-read-shape")
        return canonical([workspace, desired, revision, attempts])

    def ready(self, sleep=time.sleep):
        from urllib.error import HTTPError, URLError
        from urllib.request import ProxyHandler, Request, build_opener
        from control_plane_kit_servers_cpk_server.client.transport import _RejectRedirects
        opener = build_opener(ProxyHandler({}), _RejectRedirects())
        deadline = time.monotonic() + 20
        while True:
            try:
                with opener.open(Request("http://127.0.0.1:18163/health/ready"), timeout=3) as response:
                    raw = response.read(1025)
                    require(response.status == 200 and len(raw) <= 1024, "readiness")
                    value = json.loads(raw)
                    require(all(value.get(k) == v for k, v in {
                        "status": "ready", "application": "configured", "stores": "configured"}.items()),
                        "readiness")
                return
            except HTTPError:
                raise Hold("readiness") from None
            except (URLError, ConnectionError, TimeoutError):
                require(time.monotonic() < deadline, "readiness")
                sleep(0.2)


class OwnerUidReads:
    """UID501 child in the same approved helper; no credential in args/files."""

    def __init__(self, approved_digest, spawn=None):
        self.digest = approved_digest
        self.spawn = spawn or spawn_as_owner

    def bind_identity(self, configured_document):
        self.document = configured_document

    def saved(self):
        admin, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        admin.settimeout(10)
        process = None
        failure, output, outcomes = None, None, []
        try:
            process = self.spawn([sys.executable, __file__, "--read-saved", self.digest,
                                  "--admin-fd", str(child.fileno())], pass_fds=(child.fileno(),))
            child.close()
            credential = credential_from_owner_channel(admin)
            require(credential_identity(self.document, credential) == {
                "issuer": "urn:control-plane-kit:static-development",
                "subject_id": "cpk163-gparent-20261109-human", "kind": "operator"}, "verification-identity")
            admin.sendall(b"human-verified\n")
            output, _error = process.communicate(timeout=35)
            require(process.returncode == 0 and len(output) <= 8_388_608, "owner-client-read")
        except Hold as error:
            failure = error
        except (TimeoutError, subprocess.TimeoutExpired):
            failure = Hold("owner-client-timeout")
        except BaseException:
            failure = Hold("owner-client-unverified")
        finally:
            admin.close()
            child.close()
            if process is not None and process.poll() is None:
                try:
                    process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    outcomes = settle_owned_child(process, "reader")
            if process is not None:
                close_child_handles(process)
        if outcomes:
            raise ChildOutcomeError(outcomes)
        if failure is not None:
            raise failure
        return canonical(json.loads(output))

    def ready(self):
        SavedReads.ready(self)


def run_as_owner(argv, private_input, timeout=35):
    process = spawn_as_owner(argv)
    try:
        output, error = process.communicate(private_input, timeout=timeout)
        return subprocess.CompletedProcess(argv, process.returncode, output, error)
    except subprocess.TimeoutExpired:
        raise ChildOutcomeError(settle_owned_child(process, "evidence-or-owner-worker")) from None
    finally:
        close_child_handles(process)


def spawn_as_owner(argv, pass_fds=()):
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               user=501, group=20, extra_groups=[], pass_fds=pass_fds)
    try:
        process.cpk_pidfd = os.pidfd_open(process.pid)
    except BaseException:
        raise ChildOutcomeError([dict(role="owner-process-admission", pid=process.pid,
            reaped=process.poll() is not None, outcome="pidfd-unavailable")]) from None
    return process


def close_child_handles(process):
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            stream.close()
    if process.cpk_pidfd is not None:
        os.close(process.cpk_pidfd)
        process.cpk_pidfd = None


def settle_owned_child(process, role):
    outcomes = []
    signal_state = "not-needed"
    if process.poll() is None:
        # Signal from the child's own UID, with a pidfd so a delayed helper can
        # never signal a reused PID. No CAP_KILL or SIGKILL escalation is added.
        terminator = None
        try:
            terminator = spawn_as_owner([sys.executable, __file__, "--signal-owned-child", str(process.cpk_pidfd)],
                                        pass_fds=(process.cpk_pidfd,))
            signal_output, _error = terminator.communicate(timeout=3)
            signal_state = ("sent" if signal_output == b"signalled\n" else "already-exited"
                            if signal_output == b"already-exited\n" else "unverified") if terminator.returncode == 0 else "unverified"
        except subprocess.TimeoutExpired:
            outcomes.append(dict(role="termination-helper", pid=terminator.pid,
                                 reaped=False, outcome="unknown-after-timeout"))
            signal_state = "unverified"
        except ChildOutcomeError as error:
            outcomes.extend(error.outcomes)
            signal_state = "unverified"
        except BaseException:
            signal_state = "unverified"
        finally:
            if terminator is not None:
                close_child_handles(terminator)
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            outcomes.append(dict(role=role, pid=process.pid, reaped=False,
                                 outcome="unknown-after-timeout", signal=signal_state))
    if process.poll() is not None:
        outcomes.append(dict(role=role, pid=process.pid, reaped=True,
                             outcome="unknown-after-timeout", signal=signal_state))
    return outcomes


def administrator_channel(descriptor):
    information = os.fstat(descriptor)
    require(descriptor >= 3 and stat.S_ISSOCK(information.st_mode), "administrator-channel")
    require(all((information.st_dev, information.st_ino) != (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
                for fd in (0, 1, 2)), "administrator-channel")
    channel = socket.socket(fileno=descriptor)
    require(channel.family == socket.AF_UNIX and channel.type == socket.SOCK_STREAM, "administrator-channel")
    pid, uid, _gid = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    require(pid == os.getppid() and uid == 0, "administrator-channel")
    channel.getpeername()  # A listening/unconnected socket is not a channel.
    channel.settimeout(10)
    return channel


def channel_line(channel, maximum):
    value = bytearray()
    while b"\n" not in value:
        chunk = channel.recv(maximum + 1 - len(value))
        require(chunk and len(value) + len(chunk) <= maximum, "owner-channel-framing")
        value.extend(chunk)
    return bytes(value)


def credential_from_owner_channel(channel):
    value = channel_line(channel, 65)
    require(len(value) == 65 and value[-1] == 10, "owner-channel-framing")
    return bytes(value[:-1])


def owner_read_batch(path, channel):
    require(os.getuid() == 501 and os.getgid() == 20, "reader-owner")
    # The inherited private socket is validated before loading any credential.
    with administrator_channel(os.dup(channel.fileno())) as private:
        reader = SavedReads(path)
        credential = reader.owner_credential()
        private.sendall(credential + b"\n")
        require(channel_line(private, 32) == b"human-verified\n", "verification-denied")
        reader.accept_verified(credential)
        print(reader.saved().decode())


def inspect(api, identity):
    return api.inspect_container(identity)


def credential_identity(configured_document, credential):
    # Reuse the selected product's pure decoder/verifier; do not decode or invent
    # authentication policy or construct an application in maintenance code.
    from control_plane_kit_servers_cpk_server.server import _static_principals
    from control_plane_kit_servers_cpk_server.authentication import StaticDevelopmentMultiCredentialVerifier
    principal = StaticDevelopmentMultiCredentialVerifier(
        _static_principals(configured_document, allow_empty_grants=True)).authenticate(credential)
    return dict(issuer=principal.identity.issuer, subject_id=principal.identity.subject_id,
                kind=principal.identity.kind.value)


def network_contract(api, expected_owner):
    network = api.inspect_network(NETWORK)
    require(network["Id"] == NETWORK and all(network["Labels"].get(k) == v for k, v in LABELS.items()),
            "network-ownership")
    members = network.get("Containers", {})
    require(len(members) <= 12, "network-membership")
    owners = []
    for identity in members:
        require(re.fullmatch(r"[0-9a-f]{64}", identity), "network-membership")
        member = inspect(api, identity)
        if any(n["NetworkID"] == NETWORK and NODE in (n.get("Aliases") or [])
               for n in member["NetworkSettings"]["Networks"].values()):
            owners.append(identity)
    require(owners == ([] if expected_owner is None else [expected_owner]), "semantic-alias-owner")


def labels(value):
    value = {} if value is None else value
    require(type(value) is dict and all(type(k) is str and type(v) is str for k, v in value.items()), "labels")
    return value


def successor_config(old, image, env):
    image_labels = labels(image["Config"].get("Labels"))
    require(all(k not in image_labels or image_labels[k] == v for k, v in LABELS.items()), "label-conflict")
    require(not {"org.openj92.cpk.maintenance", "org.openj92.cpk.replaces"} & image_labels.keys(), "label-conflict")
    config = {k: deepcopy(old["Config"][k]) for k in (
        "User", "WorkingDir", "Cmd", "Entrypoint", "ExposedPorts", "StopSignal") if k in old["Config"]}
    config.update(Image=IMAGE, Env=[k + "=" + v for k, v in (env | {"CPK_MCP_PROFILE": PROFILE}).items()],
        Labels=image_labels | LABELS | {"org.openj92.cpk.maintenance": RUN, "org.openj92.cpk.replaces": OLD},
        HostConfig={k: deepcopy(old["HostConfig"][k]) for k in HOST_FIELDS if k in old["HostConfig"]},
        NetworkingConfig={"EndpointsConfig": {NETWORK: {"Aliases": [NODE]}}})
    canonical(config)  # Prove serializability in memory before any outage.
    return config


def cutover(api, reads, journal, public_plan, socket_gid, sleep=time.sleep):
    require(api.info()["ID"] == ENGINE, "engine")
    old = inspect(api, OLD)
    require(old["Id"] == OLD and old["Name"] == "/" + NAME and old["Image"] == OLD_IMAGE,
            "historical-identity")
    require(old["State"]["Running"] is True and not old["State"]["Paused"]
            and not old["State"]["Restarting"], "historical-state")
    journal.original_state = "running-observed"
    require(all(old["Config"]["Labels"].get(k) == v for k, v in LABELS.items()), "ownership")
    process_contract(old["Config"])
    host_contract(old["HostConfig"], socket_gid)
    actual_mounts(old)
    require(old["NetworkSettings"]["Ports"] == PORTS, "effective-ports")
    networks = old["NetworkSettings"]["Networks"]
    require(len(networks) == 1 and next(iter(networks.values()))["NetworkID"] == NETWORK
            and NODE in next(iter(networks.values()))["Aliases"], "semantic-alias")
    network_contract(api, OLD)
    require(not api.containers(all=True, filters={"name": "^/" + BACKUP + "$"}) and
            not api.containers(all=True, filters={"label": "org.openj92.cpk.maintenance=" + RUN}), "prior-attempt")
    old_image, image = api.inspect_image(OLD_IMAGE), api.inspect_image(IMAGE)
    require(old_image["Id"] == OLD_IMAGE and image["Id"] == IMAGE and image["Os"] == "linux"
            and image["Architecture"] == "amd64", "image")
    process_contract(image["Config"])
    require(labels(old["Config"].get("Labels")) == (labels(old_image["Config"].get("Labels")) | LABELS), "ownership")
    env = environment(old["Config"])
    node = next(n for n in public_plan["resources"]["nodes"] if n["node_id"] == NODE)
    declared = node["environment"]
    expected_names = set(environment(old_image["Config"])) | set(declared) | {
        "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON", "PGPASSWORD"}
    require(set(env) == expected_names and "CPK_MCP_PROFILE" not in env, "environment-shape")
    require(all(env.get(k) == v for k, v in declared.items()), "public-wiring")
    require(all(env.get(k) == v for k, v in environment(old_image["Config"]).items()
                if k not in declared), "base-environment")
    require(env["PGPASSWORD"] and env["CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"], "private-wiring")
    for volume in MOUNTS:
        observed = api.inspect_volume(volume)
        require(observed["Name"] == volume and all(observed["Labels"].get(k) == v for k, v in LABELS.items()),
                "volume-ownership")
    config = successor_config(old, image, env)
    journal.stage = "bind-verification-identity"
    reads.bind_identity(env["CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"])
    journal.stage = "saved-revision-before-stop"
    before = reads.saved()  # Exactly once; any failure/mismatch precedes outage.
    journal.event("preflight-verified")
    # Graceful SIGTERM only, no Docker stop escalation to SIGKILL.
    journal.stage = journal.pending = "stop-original"
    journal.original_state = "stop-outcome-unknown"
    journal.event("dispatch-intent")
    api.kill(OLD, signal="SIGTERM")
    deadline = time.monotonic() + 30
    while True:
        stopped = inspect(api, OLD)
        if not stopped["State"]["Running"]:
            break
        require(time.monotonic() < deadline, "stop-timeout")
        sleep(0.2)
    journal.original_state = "stopped-observed"
    journal.event("stop-observed", pending=None)
    journal.pending = None
    require(stopped["State"]["ExitCode"] == 0, "graceful-exit")
    journal.effect("retain-original-name", lambda: api.rename(OLD, BACKUP))
    require(inspect(api, OLD)["Name"] == "/" + BACKUP, "retention")
    journal.original_retained = True
    # Docker documents ordinary network disconnect for running containers only.
    # Do not force-disconnect retained stopped compute. Require authoritative
    # absence of its active endpoint and semantic alias before creating another.
    network_contract(api, None)
    require(OLD not in api.inspect_network(NETWORK).get("Containers", {}), "old-endpoint")
    require(not api.containers(filters={"publish": "18163"}), "port-not-released")
    journal.create(lambda: api.create_container_from_config(config, name=NAME))
    journal.stage = "verify-stopped-successor"
    new = inspect(api, journal.new_id)
    require(new["Id"] == journal.new_id and new["Image"] == IMAGE and new["Name"] == "/" + NAME
            and not new["State"]["Running"], "successor-identity")
    process_contract(new["Config"])
    host_contract(new["HostConfig"], socket_gid)
    actual_mounts(new)
    require(all(new["Config"].get(k) == config[k] for k in ("User", "Cmd", "Entrypoint", "WorkingDir", "Env", "Labels")),
            "successor-private-or-public-config")
    require(all(new["HostConfig"].get(k) == config["HostConfig"].get(k) for k in HOST_FIELDS), "successor-host-config")
    require(len(new["NetworkSettings"]["Networks"]) == 1 and any(
        n.get("NetworkID") in ("", NETWORK) and NODE in (n.get("Aliases") or [])
        for n in new["NetworkSettings"]["Networks"].values()),
        "successor-network-config")
    journal.event("stopped-successor-verified")
    original = inspect(api, OLD)
    journal.original_state = ("running-observed" if original["State"]["Running"] else
                              "stop-outcome-unknown" if original["State"]["Restarting"] else "stopped-observed")
    require(not original["State"]["Running"] and not original["State"]["Restarting"]
            and original["Name"] == "/" + BACKUP, "single-writer-before-start")
    network_contract(api, None)
    journal.started = True  # Even a failed/unavailable start may have run schema work.
    journal.effect("start-successor", lambda: api.start(journal.new_id))
    journal.stage = "verify-effective-successor"
    new = inspect(api, journal.new_id)
    require(new["State"]["Running"] and not new["State"]["Paused"] and not new["State"]["Restarting"]
            and new["NetworkSettings"]["Ports"] == PORTS and new["Path"] == "python"
            and new["Args"] == COMMAND[1:], "effective-process")
    original = inspect(api, OLD)
    journal.original_state = "running-observed" if original["State"]["Running"] else "stopped-observed"
    require(not original["State"]["Running"], "single-writer")
    network_contract(api, journal.new_id)
    actual_mounts(new)
    require(environment(new["Config"]) == env | {"CPK_MCP_PROFILE": PROFILE}, "effective-profile")
    # Inspect actual PID1 from inside its process namespace, with fixed output.
    verification = ('from pathlib import Path; '
        'ok=Path("/proc/1/cmdline").read_bytes()==b"python\\0-m\\0control_plane_kit_servers_cpk_server.server\\0" '
        'and next(x for x in Path("/proc/1/status").read_text().splitlines() if x.startswith("Uid:")).split()[1:]==["10001"]*4; '
        'print("verified" if ok else "mismatch"); raise SystemExit(0 if ok else 1)')
    check = api.exec_create(journal.new_id, ["python", "-c", verification], stdout=True, stderr=False)
    require(api.exec_start(check["Id"]).strip() == b"verified" and api.exec_inspect(check["Id"])["ExitCode"] == 0,
            "effective-user")
    journal.stage = "readiness-after-start"
    reads.ready()
    journal.stage = "saved-revision-after-start"
    require(reads.saved() == before, "saved-state-changed")
    journal.event("named-saved-records-verified")


def main(reader_channel=None):
    # No environmental credential variables or generic command switches accepted.
    require((len(sys.argv) == 3 and sys.argv[1] == "--execute-reviewed-cutover") or
            (len(sys.argv) == 5 and sys.argv[1] == "--read-saved" and reader_channel is not None), "invocation")
    plan_raw = Path("/proposal/action.json").read_bytes()
    require(re.fullmatch(r"[0-9a-f]{64}", sys.argv[2]) and
            hashlib.sha256(plan_raw).hexdigest() == sys.argv[2], "unfrozen-action-plan")
    plan = json.loads(plan_raw)
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", plan["approval_reference"])
            and plan["quiescence_confirmed"] is True and plan["exposure_reviewed"] is True
            and plan["private_wiring_reuse_approved"] is True
            and plan["verification_bearer_use_approved"] is True
            and plan["script_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "authority")
    require(not any(value for key, value in os.environ.items() if key.lower() in
                    {"http_proxy", "https_proxy", "all_proxy"}), "proxy-environment")
    raw = Path("/proposal/bootstrap.json").read_bytes()
    require(PUBLIC_PLAN_SHA and hashlib.sha256(raw).hexdigest() == PUBLIC_PLAN_SHA, "bootstrap-input")
    logging.disable(logging.CRITICAL)
    if sys.argv[1] == "--read-saved":
        owner_read_batch(Path("/credentials/human.bearer"), reader_channel)
        return 0
    require(os.getuid() == 0, "maintenance-owner")
    probe = os.pidfd_open(os.getpid())
    os.close(probe)
    import docker
    api = docker.APIClient(base_url="unix:///var/run/docker.sock", version="auto", timeout=30)
    journal = Journal(Path("/evidence") / "maintenance", plan["approval_reference"], owner=(501, 20))
    success, code = False, "unexpected"
    try:
        cutover(api, OwnerUidReads(sys.argv[2]), journal, json.loads(raw),
                os.stat("/var/run/docker.sock").st_gid)
        success, code = True, "complete"
    except ChildOutcomeError as error:
        for outcome in error.outcomes:
            if outcome not in journal.child_outcomes:
                journal.child_outcomes.append(outcome)
        code = str(error)
    except Hold as error:
        code = str(error)
    except BaseException:
        code = "provider-or-transport-failure"
    try:
        result = journal.finish(success, code)
        result["evidence_persisted"] = not any(not child["reaped"] for child in journal.child_outcomes)
    except BaseException:
        result = journal.outcome(False, "evidence-write-unverified")
        result["evidence_persisted"] = False
        success = False
    api.close()
    print(canonical(result).decode())
    return 0 if success else 1


def entry_point():
    reader_channel = None
    if len(sys.argv) >= 2 and sys.argv[1] == "--read-saved":
        try:
            require(len(sys.argv) == 5 and sys.argv[3] == "--admin-fd", "administrator-channel")
            reader_channel = administrator_channel(int(sys.argv[4]))
        except BaseException:
            print('{"schema":"cpk399.maintenance.v1","status":"HOLD","reason":"reader-channel-refused","retry":false}')
            return 1
    # Internal roles are owner-matched and carry no general provider authority.
    try:
        if len(sys.argv) == 4 and sys.argv[1] == "--write-evidence":
            require((os.getuid(), os.getgid()) == (501, 20), "evidence-owner")
            raw_evidence = sys.stdin.buffer.read(8193)
            require(len(raw_evidence) <= 8192, "evidence-bound")
            write_evidence(Path(sys.argv[3]), sys.argv[2], json.loads(raw_evidence))
            print("recorded")
            status = 0
        elif len(sys.argv) == 3 and sys.argv[1] == "--signal-owned-child":
            require((os.getuid(), os.getgid()) == (501, 20), "signal-owner")
            descriptor = int(sys.argv[2])
            require(descriptor >= 3 and os.readlink("/proc/self/fd/" + str(descriptor)) == "anon_inode:[pidfd]",
                    "owned-child-handle")
            try:
                signal.pidfd_send_signal(descriptor, signal.SIGTERM)
            except ProcessLookupError:
                print("already-exited")
                status = 0  # The exact referenced process has already exited.
            else:
                print("signalled")
                status = 0
        else:
            status = main(reader_channel)
    except ChildOutcomeError as error:
        print(canonical(dict(schema="cpk399.maintenance.v1", status="HOLD", retry=False,
                             reason="owned-child-admission-unverified", child_outcomes=error.outcomes)).decode())
        status = 1
    except BaseException:
        print('{"schema":"cpk399.maintenance.v1","status":"HOLD","reason":"invocation-or-outcome-unverified","retry":false}')
        status = 1
    finally:
        if reader_channel is not None:
            reader_channel.close()
    return status


if __name__ == "__main__":
    sys.exit(entry_point())
