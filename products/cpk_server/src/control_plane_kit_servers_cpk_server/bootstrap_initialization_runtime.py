"""One-shot initializer helpers within the existing private acquisition receipt."""
import hashlib
import io
import os
import re
import tarfile
from datetime import datetime

from .bootstrap import RootBootstrapError, RootBootstrapHold, decode_document
from .bootstrap_initialization import (
    PROGRESS_PATH, PROGRESS_SCHEMA, TARGET_SCHEMA, database_target, helper_input_bytes, package_correlation,
)
from .bootstrap_runtime import _locked, _material, _receipt, _save


_INPUT_NAMES = ("plan.json", "workspace-intent.json", "workspace-authority.json", "credential",
    "database-password", "acquisition.json")


def helper_names(plan, *, inspection=False):
    name = plan["resources"]["network"]["name"] + ("-workspace-inspect" if inspection else "-workspace-initialize")
    names = (*_INPUT_NAMES, "principals.json") if plan["input"]["installation"].get(
        "control_auth", {}).get("kind") == "multi-principal" else _INPUT_NAMES
    return name, {filename: name + "-" + filename.replace(".", "-") for filename in names}


def _target(plan, receipt, client):
    if (receipt["plan_digest"] != plan["digest"] or receipt["driver_image_id"] != plan["driver_image_id"]
            or client.info()["ID"] != receipt["engine_id"]
            or (os.environ.get("CPK_BOOTSTRAP_ENGINE_ID") is not None
                and os.environ["CPK_BOOTSTRAP_ENGINE_ID"] != receipt["engine_id"])):
        raise RootBootstrapHold("bootstrap initialization target differs")
    labels = receipt["labels"]
    if (set(labels) != set(plan["resources"]["labels"]) | {"org.openj92.cpk.acquisition"}
            or any(labels[key] != value for key, value in plan["resources"]["labels"].items())
            or re.fullmatch(r"[0-9a-f]{32}", labels["org.openj92.cpk.acquisition"]) is None):
        raise RootBootstrapHold("bootstrap initialization target differs")
    pg = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["postgres_node_id"])
    if receipt["observations"].get("fresh_postgres_volumes") != [item["name"] for item in pg["data_volumes"]]:
        raise RootBootstrapHold("bootstrap initialization lacks fresh resource evidence")
    identity = receipt["resources"]["containers"][pg["node_id"]]["id"]
    container = client.containers.get(identity)
    container.reload()
    if (container.id != identity or container.attrs["Image"] != receipt["observations"]["images"][pg["node_id"]]
            or container.attrs["Config"].get("Labels") != labels
            or container.attrs["State"].get("Running") is not True):
        raise RootBootstrapHold("bootstrap initialization target differs")
    expected = [(item["name"], item["target"], True) for item in pg["data_volumes"]]
    expected.extend((item["name"], item["target"], False) for item in (*pg["secret_files"], *pg["configuration_files"]))
    mounts = container.attrs["Mounts"]
    if (len(mounts) != len(expected) or any(item.get("Type") != "volume" for item in mounts)
            or sorted((item.get("Name"), item.get("Destination"), item.get("RW")) for item in mounts)
            != sorted(expected)):
        raise RootBootstrapHold("bootstrap initialization data mounts differ")
    for name, _, _ in expected:
        resource_id = receipt["resources"]["volumes"][name]["id"]
        resource = client.volumes.get(resource_id)
        if resource.id != resource_id or resource.id != name or resource.attrs.get("Labels") != labels:
            raise RootBootstrapHold("bootstrap initialization volume ownership differs")
    driver = client.images.get(plan["driver_image_id"])
    if driver.id != plan["driver_image_id"]:
        raise RootBootstrapHold("bootstrap initialization driver differs")
    return {"schema": TARGET_SCHEMA, "plan_digest": plan["digest"],
        "driver_image_id": plan["driver_image_id"], "installation_id": plan["input"]["installation"]["installation_id"],
        "engine_id": receipt["engine_id"], "postgres_container_id": identity,
        "postgres_image_id": container.attrs["Image"], "labels": labels,
        "data_volumes": [{**item, "id": receipt["resources"]["volumes"][item["name"]]["id"]}
            for item in pg["data_volumes"]], **database_target(plan), **package_correlation()}


def _helper_uid(plan, receipt, sdk):
    image = sdk.inspect_image(receipt["observations"]["images"][plan["cpk_node_id"]])
    uid = None if image is None else image.secret_file_owner_uid()
    if (image is None or image.image_id != receipt["observations"]["images"][plan["cpk_node_id"]]
            or type(uid) is not int or not 0 < uid < 2**31):
        raise RootBootstrapHold("bootstrap initialization helper user differs")
    return uid


def _verify_helper(helper, plan, target, record, mounts, *, stopped=False):
    helper.reload()
    attrs = helper.attrs
    host = attrs["HostConfig"]
    command = ["python", "-m", "control_plane_kit_servers_cpk_server.bootstrap_cli",
        "inspect-workspace-initialization" if "pending" in record else "initialize-workspace"]
    if (helper.id != record["helper_id"] or attrs["Image"] != plan["driver_image_id"]
            or attrs["Config"].get("Labels") != target["labels"]
            or attrs["Config"].get("User") != str(record["uid"]) or attrs["Config"].get("Cmd") != command
            or host.get("NetworkMode") != "container:" + target["postgres_container_id"]
            or host.get("Privileged") is not False or host.get("ReadonlyRootfs") is not True
            or host.get("CapAdd") not in (None, [])
            or host.get("CapDrop") != ["ALL"] or host.get("SecurityOpt") != ["no-new-privileges:true"]
            or host.get("PortBindings") not in (None, {})
            or (stopped and attrs["State"].get("Running") is not False)):
        raise RootBootstrapHold("bootstrap initialization helper ownership differs")
    configured = host.get("Mounts", [])
    def mount_key(value):
        return (value.get("Type"), value.get("Source"), value.get("Target"), value.get("ReadOnly"),
            value.get("VolumeOptions", {}).get("Subpath"))
    if (len(configured) != len(mounts) or sorted(map(mount_key, configured)) != sorted(map(mount_key, mounts))):
        raise RootBootstrapHold("bootstrap initialization helper mounts differ")
    actual = attrs["Mounts"]
    if (len(actual) != len(mounts) or any(value.get("Type") != "volume" or value.get("RW") is not False for value in actual)
            or sorted((value.get("Name"), value.get("Destination")) for value in actual)
            != sorted((value["Source"], value["Target"]) for value in mounts)):
        raise RootBootstrapHold("bootstrap initialization helper mounts differ")


def _progress(helper, plan, target, uid):
    chunks, _ = helper.get_archive(PROGRESS_PATH)
    raw = bytearray()
    try:
        for chunk in chunks:
            if len(raw) + len(chunk) > 32768:
                raise RootBootstrapHold("bootstrap initialization progress exceeds its bound")
            raw.extend(chunk)
    finally:
        if hasattr(chunks, "close"):
            chunks.close()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        entries = archive.getmembers()
        if (len(entries) != 1 or not entries[0].isfile() or entries[0].name != "progress.json"
                or not 0 < entries[0].size <= 4096 or entries[0].mode != 0o600 or entries[0].uid != uid):
            raise RootBootstrapHold("bootstrap initialization progress ownership differs")
        value = decode_document(archive.extractfile(entries[0]).read(4097))
    if (set(value) != {"schema", "plan_digest", "installation_id", "operations_commit", "schema_sha256",
            "schema_acknowledged", "initialization", "occurred_at", "pending"}
            or value["schema"] != PROGRESS_SCHEMA or value["plan_digest"] != plan["digest"]
            or value["installation_id"] != target["installation_id"]
            or value["operations_commit"] != target["operations_commit"]
            or value["schema_sha256"] != target["schema_sha256"]
            or type(value["schema_acknowledged"]) is not bool
            or value["initialization"] not in ("unknown", "matching", "missing", "conflict")
            or value["pending"] not in (None, "schema", "initialization", "inspection")):
        raise RootBootstrapHold("bootstrap initialization progress differs")
    if value["initialization"] == "matching":
        stamp = value["occurred_at"]
        if (type(stamp) is not str or re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", stamp) is None):
            raise RootBootstrapHold("bootstrap initialization progress differs")
        datetime.fromisoformat(stamp)
        if value["pending"] is not None:
            raise RootBootstrapHold("bootstrap initialization progress differs")
    elif value["occurred_at"] is not None:
        raise RootBootstrapHold("bootstrap initialization progress differs")
    return value


def _run_helper(plan, material, intent, state, receipt, client, sdk, *, inspection):
    import docker
    from control_plane_kit_core.secrets import SecretFileMode, SecretValue
    from control_plane_kit_interpreters.docker import DockerSdkSecretMount

    target = _target(plan, receipt, client)
    uid = _helper_uid(plan, receipt, sdk)
    name, names = helper_names(plan, inspection=inspection)
    if (client.containers.list(all=True, filters={"name": "^/" + name + "$"})
            or any(sdk.inspect_volume(value) is not None for value in names.values())):
        raise RootBootstrapHold("bootstrap initialization helper resources already exist")
    key = "initialization_inspection" if inspection else "initialization_helper"
    if key in receipt:
        raise RootBootstrapHold("bootstrap initialization helper requires investigation")
    record = {"helper_id": None, "uid": uid, "temporary_volumes": {}, "observation": None,
        "helper_removed": False, "cleanup": "not-started"}
    if inspection:
        record["pending"] = None
    receipt[key] = record
    _save(state, receipt)

    def effect(stage, action):
        (record if inspection else receipt)["pending"] = stage
        _save(state, receipt)
        return action()

    def observed():
        (record if inspection else receipt)["pending"] = None
        _save(state, receipt)

    values = helper_input_bytes(plan, intent, material, target)
    for filename, volume_name in names.items():
        volume = effect("create-initialization-volume:" + filename,
            lambda: client.volumes.create(name=volume_name, labels=receipt["labels"]))
        record["temporary_volumes"][volume_name] = {"id": volume.id, "removed": False}
        _save(state, receipt)
        if volume.id != volume_name or volume.attrs.get("Labels") != receipt["labels"]:
            raise RootBootstrapHold("bootstrap initialization volume ownership differs")
        observed()
        value = SecretValue(values[filename].decode("utf-8"))
        effect("materialize-initialization-file:" + filename,
            lambda: sdk.materialize_secret_file(volume_name, value, SecretFileMode.OWNER_READ_ONLY, owner_uid=uid))
        evidence = sdk.inspect_secret_file(volume_name)
        if (evidence is None or not evidence.regular_file or evidence.uid != uid or evidence.mode != 0o400
                or evidence.content_digest != hashlib.sha256(values[filename]).hexdigest()):
            raise RootBootstrapHold("bootstrap initialization input custody differs")
        observed()
    # Provider identity/resource custody are re-observed immediately before the
    # helper can be created and again before its one start. No helper has a socket.
    if _target(plan, receipt, client) != target:
        raise RootBootstrapHold("bootstrap initialization target differs")
    mounts = [dict(DockerSdkSecretMount("/bootstrap/" + filename, volume).docker_mount())
        for filename, volume in names.items()]
    helper = effect("create-initialization-helper", lambda: client.containers.create(
        plan["driver_image_id"], name=name, user=str(uid), labels=receipt["labels"],
        network_mode="container:" + target["postgres_container_id"],
        command=["python", "-m", "control_plane_kit_servers_cpk_server.bootstrap_cli",
            "inspect-workspace-initialization" if inspection else "initialize-workspace"],
        mounts=mounts, read_only=True, tmpfs={"/tmp": "rw,noexec,nosuid,size=1m,mode=1777"},
        cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
        log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"})))
    record["helper_id"] = helper.id
    _save(state, receipt)
    _verify_helper(helper, plan, target, record, mounts, stopped=True)
    observed()
    if _target(plan, receipt, client) != target:
        raise RootBootstrapHold("bootstrap initialization target differs")
    effect("inspect-workspace-initialization" if inspection else "initialize-workspace", helper.start)
    try:
        result = helper.wait(timeout=120)
    finally:
        try:
            _verify_helper(helper, plan, target, record, mounts)
            progress = _progress(helper, plan, target, uid)
            record["observation"] = progress
            if not inspection:
                receipt["observations"]["initialization"] = progress
        except Exception:
            record["readback"] = "unavailable; prior evidence retained"
        _save(state, receipt)
    progress = record["observation"]
    if (result.get("StatusCode") != 0 or progress is None or progress["pending"] is not None
            or progress["initialization"] not in (("matching", "missing", "conflict") if inspection else ("matching",))
            or (not inspection and not progress["schema_acknowledged"])):
        raise RootBootstrapHold("bootstrap workspace initialization requires investigation")
    observed()
    record["cleanup"] = "in-progress"
    _save(state, receipt)
    _verify_helper(helper, plan, target, record, mounts, stopped=True)
    effect("remove-initialization-helper", helper.remove)
    try:
        client.containers.get(helper.id)
    except docker.errors.NotFound:
        record["helper_removed"] = True
        observed()
    else:
        raise RootBootstrapHold("bootstrap initialization helper removal is unverified")
    for volume_name, observation in record["temporary_volumes"].items():
        volume = client.volumes.get(observation["id"])
        if volume.id != volume_name or volume.attrs.get("Labels") != receipt["labels"]:
            raise RootBootstrapHold("bootstrap initialization volume ownership differs")
        effect("remove-initialization-volume:" + volume_name, volume.remove)
        try:
            client.volumes.get(observation["id"])
        except docker.errors.NotFound:
            observation["removed"] = True
            observed()
        else:
            raise RootBootstrapHold("bootstrap initialization volume removal is unverified")
    record["cleanup"] = "complete"
    _save(state, receipt)
    return progress


def initialize_acquired_workspace(plan, material, intent, state, receipt, client, sdk):
    if (receipt.get("phase") != "acquiring" or receipt.get("pending") is not None
            or set(receipt["resources"]["containers"]) != {plan["postgres_node_id"]}):
        raise RootBootstrapHold("bootstrap initialization requires the exclusive fresh phase")
    return _run_helper(plan, material, intent, state, receipt, client, sdk, inspection=False)


def inspect_initialization(plan, index_path, state):
    try:
        with _locked(state):
            receipt = _receipt(state)
            if receipt.get("plan_digest") != plan["digest"] or receipt.get("driver_image_id") != plan["driver_image_id"]:
                raise RootBootstrapHold("bootstrap initialization target differs")
            previous = receipt.get("initialization_inspection")
            if previous is not None:
                if previous.get("cleanup") == "complete" and previous.get("pending") is None:
                    return {"status": "retained-inspection", "receipt": receipt}
                raise RootBootstrapHold("bootstrap initialization inspection requires investigation")
            material, intent = _material(plan, index_path)
            if intent is None:
                raise RootBootstrapHold("bootstrap initialization requires dynamic authority")
            import docker
            from control_plane_kit_interpreters.docker import DockerSdkClient
            client = docker.DockerClient(base_url="unix:///var/run/docker.sock", timeout=30)
            try:
                sdk = DockerSdkClient(client=client, docker_module=docker,
                    configuration_helper_image=plan["driver_image_id"])
                _run_helper(plan, material, intent, state, receipt, client, sdk, inspection=True)
            finally:
                client.close()
            return {"status": "observed-initialization", "receipt": receipt}
    except Exception:
        failure = RootBootstrapHold("bootstrap workspace initialization inspection requires investigation")
    raise failure
