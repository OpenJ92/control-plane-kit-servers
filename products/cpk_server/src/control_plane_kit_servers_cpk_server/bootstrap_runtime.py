"""External root acquisition; never an Operations activity executor.

An interrupted stage is deliberately terminal for automatic apply. The private
receipt preserves intent and exact observations for operator investigation.
"""

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import secrets
import stat
import time

from .bootstrap import MAX_BYTES, RootBootstrapError, RootBootstrapHold, canonical, decode_document


def private_read(path: Path) -> bytes:
    try:
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("link")
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > MAX_BYTES:
                raise ValueError("permissions")
            raw = stream.read(MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError("bound")
        return raw
    except (OSError, ValueError):
        raise RootBootstrapError("bootstrap private material could not be verified") from None


def _material(plan, index_path):
    try:
        index = decode_document(private_read(index_path))
        required = set(plan["required_material"]) | set(plan["input"].get("image_pull_credentials", {}).values())
        if (set(index) != {"schema", "files"} or index["schema"] != "cpk.root-bootstrap.material.v1"
                or not isinstance(index["files"], dict) or set(index["files"]) != required):
            raise ValueError("index")
        values = {}
        for reference, filename in index["files"].items():
            if (not isinstance(filename, str) or not filename or filename in {".", ".."}
                    or Path(filename).name != filename or "\\" in filename):
                raise ValueError("filename")
            value = private_read(index_path.parent / filename).decode("utf-8")
            if "\x00" in value:
                raise ValueError("encoding")
            values[reference] = value
        return values
    except (RootBootstrapError, ValueError, TypeError, KeyError, OSError):
        raise RootBootstrapError("bootstrap material could not be verified") from None


def _save(state, receipt):
    temporary = state / "receipt.new"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(canonical(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, state / "receipt.json")
    descriptor = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _locked(state):
    state.mkdir(mode=0o700, parents=False, exist_ok=True)
    if state.is_symlink() or not state.is_dir() or state.stat().st_mode & 0o077:
        raise RootBootstrapError("bootstrap state directory must be private")
    descriptor = os.open(state / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RootBootstrapHold("bootstrap acquisition is already locked") from None
        yield
    finally:
        os.close(descriptor)


def _receipt(state):
    value = decode_document(private_read(state / "receipt.json"))
    if value.get("schema") != "cpk.root-bootstrap.receipt.v1":
        raise RootBootstrapHold("bootstrap receipt requires investigation")
    return value


def inspect_root(state: Path) -> dict:
    receipt = _receipt(state)
    # A pending receipt needs no daemon, credentials, helper or history rewrite.
    if receipt.get("phase") != "complete" or receipt.get("pending") is not None:
        return {"status": "hold", "pending": receipt.get("pending"), "receipt": receipt}
    import docker
    client = docker.DockerClient(base_url="unix:///var/run/docker.sock", timeout=30)
    try:
        if client.info()["ID"] != receipt["engine_id"]:
            raise RootBootstrapHold("bootstrap Docker engine does not match receipt")
        for kind, resources in receipt["resources"].items():
            collection = getattr(client, kind)
            for expected in resources.values():
                observed = collection.get(expected["id"])
                labels = observed.attrs.get("Config", {}).get("Labels") if kind == "containers" else observed.attrs.get("Labels")
                if not isinstance(labels, dict) or any(labels.get(key) != value for key, value in receipt["labels"].items()):
                    raise RootBootstrapHold("bootstrap resource ownership could not be verified")
                if kind == "containers" and observed.attrs["State"]["Running"] is not True:
                    raise RootBootstrapHold("bootstrap container is not running")
        return {"status": "resources-running", "receipt": receipt,
                "readiness": "previously-observed; authenticated readiness has not been rechecked"}
    except RootBootstrapHold:
        raise
    except Exception:
        raise RootBootstrapHold("bootstrap inspection could not be verified") from None
    finally:
        client.close()


def acquire_root(plan, index_path, state):
    # The prior receipt wins even if material is now absent or changed.
    if (state / "receipt.json").exists() or (state / "receipt.json").is_symlink():
        raise RootBootstrapHold("bootstrap receipt exists; inspect without redispatch")
    material = _material(plan, index_path)
    with _locked(state):
        if (state / "receipt.json").exists() or (state / "receipt.new").exists():
            raise RootBootstrapHold("bootstrap prior acquisition requires investigation")
        try:
            return _acquire(plan, material, state)
        except (RootBootstrapError, RootBootstrapHold):
            raise
        except Exception:
            raise RootBootstrapHold("bootstrap acquisition could not be verified; inspect receipt") from None


def _acquire(plan, material, state):
    import docker
    from control_plane_kit_core.secrets import (
        LocalDevelopmentSecretResolver, SecretFileMode, SecretProviderAuthority, SecretReference, SecretValue,
    )
    from control_plane_kit_core.topology import GraphDescriptorCodec
    from control_plane_kit_interpreters.docker import DockerSdkClient, DockerSdkSecretMount, DockerRegistryAuthConfig
    from control_plane_kit_interpreters.secrets import parse_image_pull_credential, resolve_secret_deliveries

    graph = GraphDescriptorCodec().decode(plan["graph"])
    resolved = {}
    for node in graph.nodes.values():
        environment, files = {}, []
        for delivery in node.secret_deliveries:
            reference = delivery.reference
            resolver = LocalDevelopmentSecretResolver(
                SecretProviderAuthority(reference.provider_id, (reference.path,)),
                {reference.reference_id: material[reference.reference_id]})
            result = resolve_secret_deliveries((delivery,), resolver=resolver)
            environment.update(result.environment)
            files.extend(result.files)
        resolved[node.node_id] = (environment, files)
    auth = {}
    for registry, reference in plan["input"].get("image_pull_credentials", {}).items():
        credential = parse_image_pull_credential(SecretValue(material[reference]))
        auth[registry] = DockerRegistryAuthConfig(credential.username, credential.password, credential.identitytoken)

    client = docker.DockerClient(base_url="unix:///var/run/docker.sock", timeout=30)
    sdk = DockerSdkClient(client=client, docker_module=docker, configuration_helper_image=plan["driver_image_id"])
    receipt = {"schema": "cpk.root-bootstrap.receipt.v1", "plan_digest": plan["digest"],
        "driver_image_id": plan["driver_image_id"], "phase": "acquiring", "pending": None,
        "labels": dict(plan["resources"]["labels"], **{"org.openj92.cpk.acquisition": secrets.token_hex(16)}),
        "resources": {"networks": {}, "volumes": {}, "containers": {}}, "observations": {}}

    def effect(stage, operation):
        receipt["pending"] = stage
        _save(state, receipt)
        result = operation()
        # Caller records observations before clearing intent.
        return result

    def observed():
        receipt["pending"] = None
        _save(state, receipt)

    def volume(name):
        resource = effect("create-volume:" + name, lambda: client.volumes.create(name=name, labels=receipt["labels"]))
        if resource.attrs.get("Labels") != receipt["labels"]:
            raise RootBootstrapHold("bootstrap volume ownership conflict")
        receipt["resources"]["volumes"][name] = {"id": resource.id}
        observed()
        return resource

    def file_volume(name, value, uid):
        volume(name)
        effect("materialize-file:" + name, lambda: sdk.materialize_secret_file(name, value, SecretFileMode.OWNER_READ_ONLY, owner_uid=uid))
        evidence = sdk.inspect_secret_file(name)
        if (evidence is None or not evidence.regular_file or evidence.uid != uid or evidence.mode != 0o400
                or evidence.content_digest != hashlib.sha256(value.reveal().encode()).hexdigest()):
            raise RootBootstrapHold("bootstrap protected delivery could not be verified")
        receipt["observations"].setdefault("protected_files", {})[name] = {"uid": uid, "mode": "0400", "verified": True}
        observed()

    try:
        receipt["engine_id"] = client.info()["ID"]
        expected_engine = os.environ.get("CPK_BOOTSTRAP_ENGINE_ID")
        if expected_engine is not None and receipt["engine_id"] != expected_engine:
            raise RootBootstrapError("bootstrap Docker context does not match mounted daemon")
        driver = sdk.inspect_image(plan["driver_image_id"])
        if driver is None or driver.image_id != plan["driver_image_id"]:
            raise RootBootstrapError("bootstrap driver image is unavailable")
        if driver.secret_file_owner_uid() != 0:
            raise RootBootstrapError("bootstrap driver requires its explicit root helper image")
        resources = plan["resources"]
        network_name = resources["network"]["name"]
        setup_name = network_name + "-setup"
        volume_names = [entry["name"] for node in resources["nodes"]
                        for entry in (*node["data_volumes"], *node["secret_files"])] + [setup_name + "-plan", setup_name + "-credential"]
        if (client.networks.list(names=[network_name])
                or any(client.containers.list(all=True, filters={"name": "^/" + name + "$"})
                       for name in [n["name"] for n in resources["nodes"]] + [setup_name])
                or any(sdk.inspect_volume(name) is not None for name in volume_names)):
            raise RootBootstrapHold("bootstrap resource already exists; adoption is not supported")
        images = {}
        for node in resources["nodes"]:
            image = sdk.inspect_image(node["image"])
            if image is None:
                registry = node["image"].split("/", 1)[0]
                effect("pull-image:" + node["node_id"], lambda: sdk.pull_image(node["image"], auth_config=auth.get(registry)))
                image = sdk.inspect_image(node["image"])
            if image is None or node["image"] not in image.repo_digests:
                raise RootBootstrapHold("bootstrap canonical image could not be verified")
            images[node["node_id"]] = image
            image.secret_file_owner_uid()
            if node["node_id"] == plan["secrets_node_id"]:
                configured = dict(entry.split("=", 1) for entry in client.images.get(image.image_id).attrs["Config"].get("Env", []) if "=" in entry)
                configured.update(node["environment"])
                if configured.get("CPK_SECRETS_PROVIDER_ID") != plan["input"]["setup"]["provider"]["provider_id"]:
                    raise RootBootstrapHold("bootstrap provider identity differs from selected image configuration")
            receipt["observations"].setdefault("images", {})[node["node_id"]] = image.image_id
            observed()
        network = effect("create-network", lambda: client.networks.create(network_name, driver="bridge", labels=receipt["labels"]))
        receipt["resources"]["networks"][network_name] = {"id": network.id}
        observed()
        for node in resources["nodes"]:
            image = images[node["node_id"]]
            environment, files = resolved[node["node_id"]]
            mounts = []
            for entry in node["data_volumes"]:
                volume(entry["name"])
                mounts.append(docker.types.Mount(entry["target"], entry["name"], type="volume"))
            for entry in node["secret_files"]:
                value = next(item.value for item in files if item.target_path == entry["target"])
                file_volume(entry["name"], value, image.secret_file_owner_uid())
                mounts.append(dict(DockerSdkSecretMount(entry["target"], entry["name"]).docker_mount()))
            options = {}
            if node["node_id"] == plan["cpk_node_id"]:
                socket_path = node["local_docker_access"]["socket"]
                mounts.append(docker.types.Mount(socket_path, socket_path, type="bind"))
                options["group_add"] = [str(os.stat(socket_path).st_gid)]
                binding = plan["input"]["host_binding"]
                options["ports"] = {"8080/tcp": (binding["address"], binding["port"])}
            container = effect("create-container:" + node["node_id"], lambda: client.containers.create(
                image.image_id, name=node["name"], environment=dict(node["environment"], **environment),
                mounts=mounts, labels=receipt["labels"], network=network.id,
                networking_config={network.id: client.api.create_endpoint_config(aliases=node["aliases"])},
                log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "2"}), **options))
            receipt["resources"]["containers"][node["node_id"]] = {"id": container.id}
            inspection = sdk.inspect_container(container.id)
            if (inspection is None or inspection.image_id != image.image_id
                    or {(item.target_path, item.volume_name) for item in inspection.readonly_secret_mounts}
                    != {(item["target"], item["name"]) for item in node["secret_files"]}):
                raise RootBootstrapHold("bootstrap recipient mounts could not be verified")
            observed()
            effect("start-container:" + node["node_id"], container.start)
            container.reload()
            if not container.attrs["State"]["Running"]:
                raise RootBootstrapHold("bootstrap container failed to start")
            observed()
            if node["node_id"] == plan["postgres_node_id"]:
                effect("observe-postgres-readiness", lambda: _postgres_ready(container))
                observed()
            for probe in node["http_checks"]:
                check = probe["check"]
                policy = check["policy"]
                for attempt in range(policy["maximum_attempts"]):
                    result = effect("observe-http:" + node["node_id"] + ":" + check["check_id"], lambda: sdk.run_http_probe(
                        network=network.id, url=probe["url"], timeout_seconds=policy["timeout_seconds"],
                        maximum_response_bytes=policy["maximum_evidence_bytes"], expected_body_sha256=check.get("expected_body_sha256")))
                    passed = (result.exit_code == 0 and result.classification == "completed"
                              and result.status_code in check["expected_statuses"]
                              and (check.get("expected_body_sha256") is None or result.body_sha256_matches is True))
                    receipt["observations"].setdefault("http_checks", {})[node["node_id"] + ":" + check["check_id"]] = {"passed": passed, "attempt": attempt + 1}
                    observed()
                    if passed:
                        break
                    time.sleep(policy["interval_seconds"])
                else:
                    raise RootBootstrapHold("bootstrap declared HTTP readiness was not observed")
        setup_uid = images[plan["cpk_node_id"]].secret_file_owner_uid()
        file_volume(setup_name + "-plan", SecretValue(canonical(plan).decode()), setup_uid)
        file_volume(setup_name + "-credential", SecretValue(material[plan["input"]["installation"]["references"]["control_credential"]]), setup_uid)
        cpk_id = receipt["resources"]["containers"][plan["cpk_node_id"]]["id"]
        helper = effect("create-public-setup-helper", lambda: client.containers.create(
            plan["driver_image_id"], name=setup_name, user=str(setup_uid), labels=receipt["labels"], network_mode="container:" + cpk_id,
            command=["python", "-m", "control_plane_kit_servers_cpk_server.bootstrap_cli", "setup"],
            mounts=[dict(DockerSdkSecretMount("/bootstrap/" + target, setup_name + "-" + suffix).docker_mount())
                    for target, suffix in (("plan.json", "plan"), ("credential", "credential"))],
            cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"})))
        receipt["setup_helper_id"] = helper.id
        observed()
        effect("public-setup", helper.start)
        result = helper.wait(timeout=240)
        if result.get("StatusCode") != 0:
            raise RootBootstrapHold("bootstrap public setup outcome requires investigation")
        output = helper.logs(stdout=True, stderr=False, tail=1)
        receipt["observations"]["public_setup"] = decode_document(output)
        observed()
        effect("remove-completed-setup-helper", helper.remove)
        receipt["setup_helper_removed"] = True
        observed()
        receipt["phase"] = "complete"
        receipt["observations"]["external_endpoint"] = "unverified"
        _save(state, receipt)
        return {"status": "local-ready", "external_endpoint": "unverified", "receipt": receipt}
    finally:
        client.close()


def _postgres_ready(container):
    for _ in range(60):
        if container.exec_run(["pg_isready", "-h", "127.0.0.1"]).exit_code == 0:
            return
        time.sleep(1)
    raise RootBootstrapHold("bootstrap PostgreSQL readiness was not observed")
