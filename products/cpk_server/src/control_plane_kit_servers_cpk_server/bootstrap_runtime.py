"""External root acquisition; never an Operations activity executor.

An interrupted stage is deliberately terminal for automatic apply. The private
receipt preserves intent and exact observations for operator investigation.
"""

from contextlib import contextmanager
import fcntl
import hashlib
import io
import os
from pathlib import Path
import re
import secrets
import stat
import tarfile
import time

from .bootstrap import (
    MAX_BYTES, RootBootstrapError, RootBootstrapHold, canonical, decode_document,
    matches_image_reference, protected_file_owner, BootstrapStage, bootstrap_stage,
)


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


@bootstrap_stage(BootstrapStage.READ_MATERIAL)
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


@bootstrap_stage(BootstrapStage.PERSIST_RECEIPT)
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
    with bootstrap_stage(BootstrapStage.LOCK_STATE):
        state.mkdir(mode=0o700, parents=False, exist_ok=True)
        if state.is_symlink() or not state.is_dir() or state.stat().st_mode & 0o077:
            raise RootBootstrapError("bootstrap state directory must be private")
        descriptor = os.open(state / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        with bootstrap_stage(BootstrapStage.LOCK_STATE):
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


def _setup_progress(client, receipt):
    """Read safe progress from the exact owned helper, without executing it."""
    if client.info()["ID"] != receipt["engine_id"]:
        raise RootBootstrapHold("bootstrap progress engine differs")
    helper = client.containers.get(receipt["setup_helper_id"])
    if (helper.id != receipt["setup_helper_id"] or helper.attrs["Image"] != receipt["driver_image_id"]
            or any(helper.labels.get(key) != value for key, value in receipt["labels"].items())):
        raise RootBootstrapHold("bootstrap progress helper ownership differs")
    chunks, _ = helper.get_archive("/tmp/cpk-bootstrap-progress/progress.json")
    archive = bytearray()
    try:
        for chunk in chunks:
            if len(archive) + len(chunk) > 131_072:
                raise RootBootstrapHold("bootstrap progress archive exceeds its bound")
            archive.extend(chunk)
    finally:
        if hasattr(chunks, "close"):
            chunks.close()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        entries = tar.getmembers()
        if (len(entries) != 1 or not entries[0].isfile() or entries[0].name != "progress.json"
                or entries[0].size > 65_536 or entries[0].mode != 0o600 or entries[0].uid != receipt["setup_uid"]):
            raise RootBootstrapHold("bootstrap progress file could not be verified")
        progress = decode_document(tar.extractfile(entries[0]).read(65_537))
    if (set(progress) != {"schema", "plan_digest", "workspace_id", "status", "pending", "commands", "reads"}
            or progress["schema"] != "cpk.root-bootstrap.setup-progress.v1"
            or progress["plan_digest"] != receipt["plan_digest"]
            or progress["workspace_id"] != receipt["setup_workspace_id"]
            or progress["status"] not in {"in-progress", "complete"}
            or not isinstance(progress["commands"], list)
            or len(progress["commands"]) > len(receipt["setup_routes"])):
        raise RootBootstrapHold("bootstrap progress coordinates differ")
    from control_plane_kit_core.products import ProductReferenceCodec
    for position, command in enumerate(progress["commands"]):
        if not isinstance(command, dict) or command.get("route") != receipt["setup_routes"][position]:
            raise RootBootstrapHold("bootstrap progress command differs")
        for key, value in command.items():
            if key == "route":
                continue
            if key == "reference":
                ProductReferenceCodec().decode(value)
            elif (key not in {"workspace_id", "current_graph_id", "desired_graph_id", "registration_id", "delivery_id", "authority_id"}
                    or not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", value)):
                raise RootBootstrapHold("bootstrap progress contains unsupported coordinates")
    pending = progress["pending"]
    if pending is not None and (len(progress["commands"]) == len(receipt["setup_routes"])
                               or pending != receipt["setup_routes"][len(progress["commands"])]):
        raise RootBootstrapHold("bootstrap progress pending command differs")
    if (not isinstance(progress["reads"], list) or len(progress["reads"]) > 128
            or any(not isinstance(route, str) or not re.fullmatch(r"read\.[a-z.-]{1,80}", route) for route in progress["reads"])):
        raise RootBootstrapHold("bootstrap progress read evidence is invalid")
    return progress


def inspect_root(state: Path) -> dict:
    receipt = _receipt(state)
    # Ordinary pending acquisition needs no daemon. Public setup can recover its
    # confirmed coordinates by reading the exact helper; never rewrite history.
    if receipt.get("phase") != "complete" or receipt.get("pending") is not None:
        if receipt.get("setup_helper_id") and not receipt.get("setup_helper_removed"):
            import docker
            client = docker.DockerClient(base_url="unix:///var/run/docker.sock", timeout=30)
            try:
                receipt["observations"]["public_setup_progress"] = _setup_progress(client, receipt)
            except Exception:
                receipt["observations"]["setup_progress_recovery"] = "unavailable; prior confirmed evidence retained"
            finally:
                client.close()
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
    with bootstrap_stage(BootstrapStage.LOCK_STATE):
        if (state / "receipt.json").exists() or (state / "receipt.json").is_symlink():
            raise RootBootstrapHold("bootstrap receipt exists; inspect without redispatch")
    material = _material(plan, index_path)
    with _locked(state):
        with bootstrap_stage(BootstrapStage.LOCK_STATE):
            if (state / "receipt.json").exists() or (state / "receipt.new").exists():
                raise RootBootstrapHold("bootstrap prior acquisition requires investigation")
        try:
            return _acquire(plan, material, state)
        except (RootBootstrapError, RootBootstrapHold):
            raise
        except Exception:
            raise RootBootstrapHold("bootstrap acquisition could not be verified; inspect receipt") from None


def _acquire(plan, material, state):
    with bootstrap_stage(BootstrapStage.LOAD_RUNTIME_DEPENDENCIES):
        import docker
        from control_plane_kit_core.secrets import (
            LocalDevelopmentSecretResolver, SecretFileMode, SecretProviderAuthority, SecretReference, SecretValue,
        )
        from control_plane_kit_core.topology import GraphDescriptorCodec
        from control_plane_kit_interpreters.docker import DockerSdkClient, DockerSdkSecretMount, DockerRegistryAuthConfig
        from control_plane_kit_interpreters.secrets import parse_image_pull_credential, resolve_secret_deliveries

    with bootstrap_stage(BootstrapStage.DECODE_GRAPH):
        graph = GraphDescriptorCodec().decode(plan["graph"])
    with bootstrap_stage(BootstrapStage.RESOLVE_DELIVERIES):
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
    with bootstrap_stage(BootstrapStage.DECODE_PULL_CREDENTIALS):
        auth = {}
        for registry, reference in plan["input"].get("image_pull_credentials", {}).items():
            credential = parse_image_pull_credential(SecretValue(material[reference]))
            auth[registry] = DockerRegistryAuthConfig(credential.username, credential.password, credential.identitytoken)

    with bootstrap_stage(BootstrapStage.CONSTRUCT_DOCKER_CLIENT):
        client = docker.DockerClient(base_url="unix:///var/run/docker.sock", timeout=30)
        sdk = DockerSdkClient(client=client, docker_module=docker, configuration_helper_image=plan["driver_image_id"])
    with bootstrap_stage(BootstrapStage.PREPARE_RECEIPT_ENVELOPE):
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
        receipt["resources"]["volumes"][name] = {"id": resource.id}
        _save(state, receipt)
        if resource.attrs.get("Labels") != receipt["labels"]:
            raise RootBootstrapHold("bootstrap volume ownership conflict")
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
        with bootstrap_stage(BootstrapStage.VERIFY_DAEMON_CONTEXT):
            receipt["engine_id"] = client.info()["ID"]
            expected_engine = os.environ.get("CPK_BOOTSTRAP_ENGINE_ID")
            if expected_engine is not None and receipt["engine_id"] != expected_engine:
                raise RootBootstrapError("bootstrap Docker context does not match mounted daemon")
        with bootstrap_stage(BootstrapStage.INSPECT_DRIVER_IMAGE):
            driver = sdk.inspect_image(plan["driver_image_id"])
            if driver is None or driver.image_id != plan["driver_image_id"]:
                raise RootBootstrapError("bootstrap driver image is unavailable")
        with bootstrap_stage(BootstrapStage.VERIFY_DRIVER_USER):
            if driver.secret_file_owner_uid() != 0:
                raise RootBootstrapError("bootstrap driver requires its explicit root helper image")
        with bootstrap_stage(BootstrapStage.CHECK_RESOURCE_CONFLICTS):
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
        file_owners = {}
        for node in resources["nodes"]:
            with bootstrap_stage(BootstrapStage.INSPECT_PRODUCT_IMAGE):
                image = sdk.inspect_image(node["image"])
            if image is None:
                registry = node["image"].split("/", 1)[0]
                effect("pull-image:" + node["node_id"], lambda: sdk.pull_image(node["image"], auth_config=auth.get(registry)))
                with bootstrap_stage(BootstrapStage.INSPECT_PRODUCT_IMAGE):
                    image = sdk.inspect_image(node["image"])
            with bootstrap_stage(BootstrapStage.VERIFY_PRODUCT_IMAGE):
                if image is None or not matches_image_reference(node["image"], image.repo_digests):
                    raise RootBootstrapHold("bootstrap canonical image could not be verified")
                images[node["node_id"]] = image
                owner = protected_file_owner(node["secret_files"], image)
                if owner is not None:
                    file_owners[node["node_id"]] = owner
            if node["node_id"] == plan["secrets_node_id"]:
                with bootstrap_stage(BootstrapStage.VERIFY_PROVIDER_IMAGE):
                    configured = dict(entry.split("=", 1) for entry in client.images.get(image.image_id).attrs["Config"].get("Env", []) if "=" in entry)
                    configured.update(node["environment"])
                    if configured.get("CPK_SECRETS_PROVIDER_ID") != plan["input"]["setup"]["provider"]["provider_id"]:
                        raise RootBootstrapHold("bootstrap provider identity differs from selected image configuration")
            receipt["observations"].setdefault("images", {})[node["node_id"]] = image.image_id
            observed()
        network = effect("create-network", lambda: client.networks.create(network_name, driver="bridge", labels=receipt["labels"]))
        receipt["resources"]["networks"][network_name] = {"id": network.id}
        _save(state, receipt)
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
                file_volume(entry["name"], value, file_owners[node["node_id"]])
                mounts.append(dict(DockerSdkSecretMount(entry["target"], entry["name"]).docker_mount()))
            options = {}
            if node["local_docker_access"] is not None:
                socket_path = node["local_docker_access"]["socket"]
                mounts.append(docker.types.Mount(socket_path, socket_path, type="bind"))
                options["group_add"] = [str(os.stat(socket_path).st_gid)]
            if node["node_id"] == plan["cpk_node_id"]:
                binding = plan["input"]["host_binding"]
                options["ports"] = {"8080/tcp": (binding["address"], binding["port"])}
            container = effect("create-container:" + node["node_id"], lambda: client.containers.create(
                image.image_id, name=node["name"], environment=dict(node["environment"], **environment),
                mounts=mounts, labels=receipt["labels"], network=network.id,
                networking_config={network.id: client.api.create_endpoint_config(aliases=node["aliases"])},
                log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "2"}), **options))
            receipt["resources"]["containers"][node["node_id"]] = {"id": container.id}
            _save(state, receipt)
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
        setup_uid = file_owners[plan["cpk_node_id"]]
        file_volume(setup_name + "-plan", SecretValue(canonical(plan).decode()), setup_uid)
        file_volume(setup_name + "-credential", SecretValue(material[plan["input"]["installation"]["references"]["control_credential"]]), setup_uid)
        cpk_id = receipt["resources"]["containers"][plan["cpk_node_id"]]["id"]
        receipt.update(setup_uid=setup_uid, setup_workspace_id=plan["input"]["installation"]["workspace_id"],
                       setup_routes=plan["setup_routes"])
        helper = effect("create-public-setup-helper", lambda: client.containers.create(
            plan["driver_image_id"], name=setup_name, user=str(setup_uid), labels=receipt["labels"], network_mode="container:" + cpk_id,
            command=["python", "-m", "control_plane_kit_servers_cpk_server.bootstrap_cli", "setup"],
            mounts=[dict(DockerSdkSecretMount("/bootstrap/" + target, setup_name + "-" + suffix).docker_mount())
                    for target, suffix in (("plan.json", "plan"), ("credential", "credential"))],
            cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"})))
        receipt["setup_helper_id"] = helper.id
        _save(state, receipt)
        observed()
        effect("public-setup", helper.start)
        try:
            result = helper.wait(timeout=240)
        finally:
            try:
                receipt["observations"]["public_setup_progress"] = _setup_progress(client, receipt)
            except Exception:
                receipt["observations"]["setup_progress_recovery"] = "unavailable; inspect exact helper"
            _save(state, receipt)
        progress = receipt["observations"].get("public_setup_progress", {})
        if (result.get("StatusCode") != 0 or progress.get("status") != "complete"
                or progress.get("pending") is not None or len(progress.get("commands", [])) != len(plan["setup_routes"])):
            raise RootBootstrapHold("bootstrap public setup outcome requires investigation")
        receipt["observations"]["public_setup"] = {"status": "authenticated-local-setup",
            "workspace_id": progress["workspace_id"], "commands": progress["commands"],
            "reads": progress["reads"], "external_endpoint": "unverified"}
        observed()
        effect("remove-completed-setup-helper", helper.remove)
        receipt["setup_helper_removed"] = True
        observed()
        for name in (setup_name + "-plan", setup_name + "-credential"):
            identity = receipt["resources"]["volumes"][name]["id"]
            staging = client.volumes.get(identity)
            if staging.id != identity or staging.attrs.get("Labels") != receipt["labels"]:
                raise RootBootstrapHold("bootstrap staging volume ownership differs")
            effect("remove-completed-setup-volume:" + name, staging.remove)
            receipt["observations"].setdefault("removed_setup_volumes", {})[name] = {"id": identity, "removed": True}
            _save(state, receipt)
            try:
                client.volumes.get(identity)
            except docker.errors.NotFound:
                del receipt["resources"]["volumes"][name]
                observed()
            else:
                raise RootBootstrapHold("bootstrap staging volume removal was not verified")
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
