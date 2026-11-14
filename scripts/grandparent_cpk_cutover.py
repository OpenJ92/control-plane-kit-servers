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
import stat
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

    def __init__(self, root, approval):
        self.root = root
        root.mkdir(mode=0o700, exist_ok=False)
        self.stream = (root / "events.jsonl").open("x")
        os.chmod(root / "events.jsonl", 0o600)
        self.approval = approval
        self.new_id = None
        self.pending = None
        self.stage = "preflight"
        self.started = False
        self.original_stopped = False

    def event(self, kind):
        self.stream.write(canonical(dict(event=kind, stage=self.stage, successor_id=self.new_id,
                                         pending=self.pending)).decode() + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def effect(self, stage, call):
        self.stage = self.pending = stage
        self.event("dispatch-intent")
        value = call()
        self.pending = None
        self.event("returned")
        return value

    def finish(self, success, code):
        # Failure remains bounded even if the provider exception contains secrets.
        result = dict(schema="cpk399.maintenance.v1", run=RUN, owner="North",
            approval_reference=self.approval, original_id=OLD, successor_id=self.new_id,
            stage=self.stage, status="verified" if success else "HOLD", reason=code,
            pending=self.pending, retry=False, rollback=False,
            startup_attempted=self.started, schema_change_possible=self.started,
            original_stopped_retained=self.original_stopped,
            saved_revision_compared=success, client_connected=False,
            historical_inspector="original-id-stopped-by-maintenance" if self.original_stopped else "not-superseded")
        with (self.root / "receipt.json").open("x") as stream:
            os.chmod(self.root / "receipt.json", 0o600)
            stream.write(canonical(result).decode() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.stream.close()
        return result


class SavedReads:
    """Two existing public reads, bounded transport; no command surface."""

    def __init__(self, credential_path):
        metadata = credential_path.lstat()
        require(stat.S_ISREG(metadata.st_mode) and not credential_path.is_symlink()
                and metadata.st_uid == 501 and stat.S_IMODE(metadata.st_mode) == 0o400
                and metadata.st_size == 64, "credential-metadata")
        self.path = credential_path

    def read(self, suffix):
        # Existing public transport owns redirects, bounded decoding and safe errors.
        from control_plane_kit_servers_cpk_server.client.profile import ClientProfile
        from control_plane_kit_servers_cpk_server.client.transport import PublicHttpTransport
        profile = ClientProfile("http://" + NODE + ":8080", WORKSPACE,
            {"operator": self.path, "approver": Path("/not-provided"), "worker": Path("/not-provided")},
            Path("/not-used"))
        transport = PublicHttpTransport(profile, timeout_seconds=5)
        route = "read.workspace" if suffix == "workspace" else "read.desired-topology-draft-revision"
        coordinates = dict(workspace_id=WORKSPACE)
        if suffix != "workspace":
            coordinates.update(draft_id=DRAFT, revision="1")
        return transport.call(route, path_parameters=coordinates, payload={}, credential_role="operator")

    def saved(self):
        workspace, revision = self.read("workspace"), self.read("revision")
        require(workspace["workspace"]["workspace_id"] == WORKSPACE and
                workspace["workspace"]["current_graph_id"] == CURRENT and
                workspace["workspace"]["desired_graph_id"] == DESIRED and
                workspace["workspace"]["desired_graph_revision"] == 1, "saved-workspace-mismatch")
        require(revision["workspace_id"] == WORKSPACE and revision["draft_id"] == DRAFT and
                revision["revision"] == 1 and revision["graph_id"] == DESIRED and
                isinstance(revision["graph_descriptor"], str), "saved-revision-mismatch")
        return canonical([workspace, revision])

    def ready(self, sleep=time.sleep):
        from urllib.error import HTTPError, URLError
        from urllib.request import ProxyHandler, Request, build_opener
        from control_plane_kit_servers_cpk_server.client.transport import _RejectRedirects
        opener = build_opener(ProxyHandler({}), _RejectRedirects())
        deadline = time.monotonic() + 20
        while True:
            try:
                with opener.open(Request("http://" + NODE + ":8080/health/ready"), timeout=3) as response:
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


def inspect(api, identity):
    return api.inspect_container(identity)


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


def cutover(api, reads, journal, public_plan, socket_gid, sleep=time.sleep):
    require(api.info()["ID"] == ENGINE, "engine")
    old = inspect(api, OLD)
    require(old["Id"] == OLD and old["Name"] == "/" + NAME and old["Image"] == OLD_IMAGE,
            "historical-identity")
    require(old["State"]["Running"] is True and not old["State"]["Paused"]
            and not old["State"]["Restarting"], "historical-state")
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
    require(old["Config"]["Labels"] == (old_image["Config"].get("Labels", {}) | LABELS), "ownership")
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
    journal.stage = "saved-revision-before-stop"
    before = reads.saved()  # Exactly once; any failure/mismatch precedes outage.
    journal.event("preflight-verified")
    # Graceful SIGTERM only, no Docker stop escalation to SIGKILL.
    journal.effect("stop-original", lambda: api.kill(OLD, signal="SIGTERM"))
    deadline = time.monotonic() + 30
    while True:
        stopped = inspect(api, OLD)
        if not stopped["State"]["Running"]:
            break
        require(time.monotonic() < deadline, "stop-timeout")
        sleep(0.2)
    require(stopped["State"]["ExitCode"] == 0, "graceful-exit")
    journal.original_stopped = True
    journal.effect("retain-original-name", lambda: api.rename(OLD, BACKUP))
    require(inspect(api, OLD)["Name"] == "/" + BACKUP, "retention")
    # Docker documents ordinary network disconnect for running containers only.
    # Do not force-disconnect retained stopped compute. Require authoritative
    # absence of its active endpoint and semantic alias before creating another.
    network_contract(api, None)
    require(OLD not in api.inspect_network(NETWORK).get("Containers", {}), "old-endpoint")
    require(not api.containers(filters={"publish": "18163"}), "port-not-released")
    config = {k: deepcopy(old["Config"][k]) for k in (
        "User", "WorkingDir", "Cmd", "Entrypoint", "ExposedPorts", "StopSignal") if k in old["Config"]}
    config.update(Image=IMAGE, Env=[k + "=" + v for k, v in (env | {"CPK_MCP_PROFILE": PROFILE}).items()],
        Labels=dict(old["Config"]["Labels"], **image["Config"].get("Labels", {}),
                    **{"org.openj92.cpk.maintenance": RUN, "org.openj92.cpk.replaces": OLD}),
        HostConfig={k: deepcopy(old["HostConfig"][k]) for k in HOST_FIELDS if k in old["HostConfig"]},
        NetworkingConfig={"EndpointsConfig": {NETWORK: {"Aliases": [NODE]}}})
    created = journal.effect("create-successor", lambda: api.create_container_from_config(config, name=NAME))
    if not (type(created) is dict and re.fullmatch(r"[0-9a-f]{64}", created.get("Id", ""))):
        journal.pending = "create-successor"
        raise Hold("create-outcome-unknown")
    journal.new_id = created["Id"]
    journal.event("successor-id-recorded")
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
        n["NetworkID"] == NETWORK and NODE in n["Aliases"] for n in new["NetworkSettings"]["Networks"].values()),
        "successor-network-config")
    journal.event("stopped-successor-verified")
    journal.started = True  # Even a failed/unavailable start may have run schema work.
    journal.effect("start-successor", lambda: api.start(journal.new_id))
    journal.stage = "verify-effective-successor"
    new = inspect(api, journal.new_id)
    require(new["State"]["Running"] and not new["State"]["Paused"] and not new["State"]["Restarting"]
            and new["NetworkSettings"]["Ports"] == PORTS and new["Path"] == "python"
            and new["Args"] == COMMAND[1:], "effective-process")
    require(not inspect(api, OLD)["State"]["Running"], "single-writer")
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


def main():
    # No environmental credential variables or generic command switches accepted.
    require(len(sys.argv) == 3 and sys.argv[1] == "--execute-reviewed-cutover", "invocation")
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
    import docker
    logging.disable(logging.CRITICAL)
    api = docker.APIClient(base_url="unix:///var/run/docker.sock", version="auto", timeout=30)
    journal = Journal(Path("/evidence") / "maintenance", plan["approval_reference"])
    success, code = False, "unexpected"
    try:
        cutover(api, SavedReads(Path("/credentials/human.bearer")), journal, json.loads(raw),
                os.stat("/var/run/docker.sock").st_gid)
        success, code = True, "complete"
    except Hold as error:
        code = str(error)
    except BaseException:
        code = "provider-or-transport-failure"
    result = journal.finish(success, code)
    api.close()
    print(canonical(result).decode())
    return 0 if success else 1


if __name__ == "__main__":
    # Refusals before the private/provider boundary also have no traceback.
    try:
        status = main()
    except BaseException:
        print('{"schema":"cpk399.maintenance.v1","status":"HOLD","reason":"preflight-refused","retry":false}')
        status = 1
    sys.exit(status)
