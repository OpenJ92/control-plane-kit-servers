"""Owning gate fixture and exact-ID cleanup for the real bootstrap.sh witness."""

import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import secrets
import signal
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import NamedTuple

from products.cpk_server.examples.root_bootstrap_input import example_input
from control_plane_kit_servers_cpk_server.bootstrap import matches_image_reference


ROOT = Path("/witness")


class ImageAccountBaseline(NamedTuple):
    image_reference: str
    config_digest: str
    passwd_sha256: str
    group_sha256: str
    uid: int
    primary_gid: int
    supplementary_gids: tuple[int, ...]

    def expected_groups(self, image_reference, socket_gid):
        assert image_reference == self.image_reference, "image account baseline does not match candidate"
        return frozenset((self.primary_gid, *self.supplementary_gids, socket_gid))


# Offline final-filesystem evidence, reviewed in Servers #170. This value is
# independent of process observations and must be resealed for another image.
CPK_IMAGE_ACCOUNT = ImageAccountBaseline(
    image_reference="ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:1ba7174ee22461566750a516dac173fdd718ed9b059660f30c3ad3f9db79d0f4",
    config_digest="sha256:d0e3f163519060efba0fcded2c0e588a3fa26781efc43692e8ef4a9646bbd2cc",
    passwd_sha256="2b154879fd6e9899bbe9f9c04eb2535f3388ad5a090f90a78c0dca81a13b9921",
    group_sha256="1ffcc10cbb13f710c78598bdccecd91b43251fef7e443ca860dfe84c656c0653",
    uid=10001, primary_gid=10001, supplementary_gids=(100,),
)


# Accepted final-filesystem evidence from #347 run40789512741, independently
# reviewed at issuecomment-6483769887. config_digest is the original registry
# config identity, not the separately recorded normalized OCI config identity.
CPK_DYNAMIC_IMAGE_ACCOUNT = ImageAccountBaseline(
    image_reference="ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:337c8cf44d1ccf624663c866f8084655ead7e8f5c62c121424c9d15f7650e370",
    config_digest="sha256:d300c4fbbe1849383d6b9c40ad8832d882f9865110d9d8e24d3556ca83070fab",
    passwd_sha256="2b154879fd6e9899bbe9f9c04eb2535f3388ad5a090f90a78c0dca81a13b9921",
    group_sha256="1ffcc10cbb13f710c78598bdccecd91b43251fef7e443ca860dfe84c656c0653",
    uid=10001, primary_gid=10001, supplementary_gids=(100,),
)


def reviewed_image_account(reference):
    # Extend only with a separately reviewed final-filesystem seal for the exact
    # published candidate. A syntactically valid tuple is not an account seal.
    for baseline in (CPK_IMAGE_ACCOUNT, CPK_DYNAMIC_IMAGE_ACCOUNT):
        if baseline.image_reference == reference:
            return baseline
    raise AssertionError("root bootstrap candidate has no reviewed image account baseline")


def prepare_dynamic_document(document, selection, driver):
    """Author fixture intent through the existing commissioning/descriptor owners."""
    from dataclasses import replace
    from control_plane_kit_core.configuration import ConfigurationArtifact
    from control_plane_kit_core.products import OciImageReference, ProductDescriptorCodec
    from control_plane_kit_servers_cpk_server.bootstrap import canonical
    from control_plane_kit_servers_cpk_server.bootstrap_workspace import workspace_intent_commitment
    from control_plane_kit_servers_cpk_server.control_configuration import CpkSourceVariant, cpk_source_runtime_contract
    from control_plane_kit_servers_cpk_server.root_commissioning import plan_root_commissioning, prepare_root_commissioning
    from control_plane_kit_servers_secrets_server.configuration import secrets_source_runtime_contract

    reviewed_image_account(selection["images"]["cpk-server"])
    installation = document["installation"]
    state = ROOT / "commissioning"
    state.mkdir(mode=0o700)
    intent = {"schema": "cpk.root-commissioning.intent.v1",
        "installation_id": installation["installation_id"], "workspace_id": installation["workspace_id"],
        "profile": "operator-offline-read-trust",
        "custody": {"host_directory": str(state), "uid": os.geteuid(), "gid": os.getegid()}}
    commissioning = plan_root_commissioning(intent, preparer_image_id=driver)
    public = prepare_root_commissioning(commissioning, expected_digest=commissioning["digest"],
        preparer_image_id=driver, state_directory=state)
    codec = ProductDescriptorCodec()
    for role in ("cpk", "secrets"):
        artifact = ConfigurationArtifact.from_descriptor(public["artifacts"][role])
        contract = (cpk_source_runtime_contract(CpkSourceVariant.DOCKER_CLOUDFLARE, artifact)
            if role == "cpk" else secrets_source_runtime_contract(artifact))
        registry_path, digest = selection["images"][role + "-server"].split("@")
        registry, repository = registry_path.split("/", 1)
        original = codec.decode_document(installation["products"][role])
        installation["products"][role] = json.loads(codec.encode_document(replace(original.product,
            image=OciImageReference(registry, repository, digest), runtime_contract=contract)).content)
    installer = {"issuer": "urn:control-plane-kit:static-development",
        "subject_id": "dynamic-root-fixture-installer", "kind": "operator"}
    policy = canonical({"schema": "cpk-server.workspace-authority.v1",
        "installation_id": installation["installation_id"], "administrators": [installer],
        "known_identities": [installer], "capabilities": ["installed-management"]})
    scopes = [scope for grant in installation["workspace_grants"] for scope in grant["scopes"]
        if scope != "hub:instance:create"]
    installation["workspace_grants"] = []
    installation["control_auth"] = {"kind": "multi-principal",
        "principals_document": "secret://bootstrap/" + installation["installation_id"] + "/principals"}
    administration = {"workspace_creation_idempotency_key": "fixture-create",
        "permission_grants": [{"target": installer, "scopes": scopes,
            "expected_revision": 0, "idempotency_key": "fixture-ordinary-grant"}],
        "management_grant": {"runtime_id": installation["installation_id"] + "-docker",
            "authority_ref": installation["runtime_authority"], "capability_id": "installed-management",
            "expected_revision": 0, "idempotency_key": "fixture-management-grant",
            "registration_from": "command.runtime-authority.register"}}
    document["setup"]["administration"] = {"permission_grant_count": 1, "management_grant": True}
    private = {"policy": {"file": "workspace-authority.json", "sha256": hashlib.sha256(policy).hexdigest()},
        "installer": installer, "initialization_idempotency_key": "fixture-initialize",
        "administration": administration}
    installation["workspace_authority"] = {"mode": "dynamic-v1",
        "private_intent_sha256": workspace_intent_commitment(policy_bytes=policy, installer=installer,
            initialization_idempotency_key=private["initialization_idempotency_key"],
            public_setup=document["setup"], administration=administration)}
    return policy, private


def numeric_group_check(primary_gid, supplementary_gids, expected_groups, socket_gid):
    observed = {primary_gid, *supplementary_gids}
    expected = set(expected_groups)
    return observed == expected, {
        "declared_socket_group_present": socket_gid in observed,
        "unexpected_groups_present": bool(observed - expected),
    }


def retain_authority_evidence(run, container, inspection, node, receipt, engine_matches):
    """Keep bounded mount evidence private; diagnostics cannot replace the law."""
    class EvidenceUnavailable(Exception):
        pass

    status = {"written": False, "complete": False}
    directory_fd = None
    try:
        def binds(values, target_key, readonly_key):
            if type(values) is not list:
                raise EvidenceUnavailable("unknown mounts")
            result = []
            for value in values:
                if type(value) is not dict:
                    raise EvidenceUnavailable("unknown mount")
                if value.get("Type") != "bind":
                    continue
                entry = {key: value.get(key) for key in ("Type", "Source", target_key, readonly_key)}
                omitted = readonly_key == "ReadOnly" and readonly_key not in value
                if omitted:
                    entry[readonly_key] = "omitted"
                if (any(type(entry[key]) is not str or not entry[key].startswith("/")
                        or len(entry[key]) > 1024 for key in ("Source", target_key))
                        or (not omitted and type(entry[readonly_key]) is not bool)):
                    raise EvidenceUnavailable("unknown or oversized bind")
                result.append(entry)
                if len(result) > 4:
                    raise EvidenceUnavailable("too many binds")
            return result

        def groups():
            values = inspection.supplementary_groups
            if (type(values) is not tuple or len(values) > 16
                    or any(type(group) is not str or not group.isascii()
                           or not group.isdecimal() or len(group) > 20 for group in values)):
                raise EvidenceUnavailable("unknown or oversized groups")
            return values

        def section(read):
            try:
                return {"known": True, "values": read()}
            except EvidenceUnavailable as error:
                return {"known": False, "reason": str(error)}
            except Exception:
                return {"known": False, "reason": "unavailable shape"}

        attrs = container.attrs
        if type(run) is not str or len(run) > 128:
            raise EvidenceUnavailable("oversized run")
        matches = {
            "engine": engine_matches,
            "container": container.id == receipt["resources"]["containers"][node["node_id"]]["id"],
            "image": attrs["Image"] == receipt["observations"]["images"][node["node_id"]],
            "labels": all(attrs["Config"]["Labels"].get(key) == value
                          for key, value in receipt["labels"].items()),
        }
        if not all(matches.values()):
            raise EvidenceUnavailable("custody mismatch")
        socket = node["local_docker_access"]["socket"]
        if socket != "/var/run/docker.sock":
            raise EvidenceUnavailable("unexpected requested socket")
        record = {
            "schema": "cpk.test.authority-mount-evidence.v1", "run": run,
            "receipt_matches": matches,
            "requested": {"Type": "bind", "Source": socket, "Target": socket, "ReadOnly": False},
            "observed": section(lambda: binds(attrs.get("Mounts"), "Destination", "RW")),
            "configured": section(lambda: binds(attrs.get("HostConfig", {}).get("Mounts"), "Target", "ReadOnly")),
            "supplementary_groups": section(groups),
        }
        payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(payload) > 4096:
            raise EvidenceUnavailable("oversized record")
        directory_fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if stat.S_IMODE(os.fstat(directory_fd).st_mode) != 0o700:
            raise EvidenceUnavailable("nonprivate directory")
        fd = os.open("authority-mount-evidence.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory_fd)
        with os.fdopen(fd, "wb") as evidence:
            if stat.S_IMODE(os.fstat(evidence.fileno()).st_mode) != 0o600:
                raise EvidenceUnavailable("nonprivate file")
            evidence.write(payload)
            evidence.flush()
            os.fsync(evidence.fileno())
        status = {"written": True,
                  "complete": all(record[key]["known"] for key in ("observed", "configured", "supplementary_groups")),
                  "actual_captured": record["observed"]["known"], "bytes": len(payload),
                  "sha256": hashlib.sha256(payload).hexdigest()}
    except EvidenceUnavailable as error:
        status.update(unavailable_or_incomplete=True, reason=str(error))
    except Exception:
        # Never print exception text: paths or provider values may be sensitive.
        status["unavailable_or_incomplete"] = True
    finally:
        if directory_fd is not None:
            try:
                os.close(directory_fd)
            except OSError:
                status.update(complete=False, unavailable_or_incomplete=True, reason="directory close failed")
    print(json.dumps({"cpk_private_authority_evidence": status}), flush=True)


def prepare(run):
    os.umask(0o077)
    from scripts.root_artifact_inputs import identity, select_root_artifacts
    selection = select_root_artifacts(dict(os.environ))
    driver = os.environ.get("CPK_ROOT_DRIVER_IMAGE_ID")
    if selection is not None:
        assert identity(driver), "dynamic root fixture requires the actual driver image ID"
        reviewed_image_account(selection["images"]["cpk-server"])
    commissioning_driver_witness(run)
    port_text = os.environ.get("CPK_ROOT_TEST_PORT", "18089")
    if not port_text.isascii() or not port_text.isdecimal() or not 1 <= int(port_text) <= 65535:
        raise ValueError("CPK_ROOT_TEST_PORT must be an integer from 1 to 65535")
    document = example_input(installation_id=run, workspace_id=run, port=int(port_text))
    from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationFileMode, ConfigurationMediaType
    # This is an inert delivery witness on historical images, not current-source
    # control configuration or qualification of a new receiving protocol.
    if selection is None:
        for role in ("cpk", "secrets"):
            artifact = ConfigurationArtifact("bootstrap-file-witness", "/etc/cpk/bootstrap-witness.json",
                ConfigurationMediaType.JSON, json.dumps({"recipient": role, "run": run}), ConfigurationFileMode.READ_ONLY)
            document["installation"]["products"][role]["product"]["runtime_contract"]["configuration_artifacts"] = [artifact.descriptor()]
    else:
        policy, private = prepare_dynamic_document(document, selection, driver)
        (ROOT / "artifact-selection.json").write_text(json.dumps(selection))
    input_path = ROOT / "input.json"
    input_path.write_text(json.dumps(document))
    # The real launcher must plan from the documented invoking-user private input.
    input_stat = input_path.stat()
    assert input_stat.st_uid == os.getuid() and input_stat.st_mode & 0o777 == 0o600
    token = secrets.token_urlsafe(48)
    values = {
        "control_credential": secrets.token_urlsafe(48),
        "postgres_password": secrets.token_urlsafe(48),
        "custody_root_key": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "provider_client_credential": token,
        "provider_credentials_document": json.dumps([{"subject": "root-bootstrap-witness", "token": token,
            "grants": [{"action": "secret.resolve", "workspace_id": run,
                        "intents": ["postgres.password", "application.control-token"]}]}]),
    }
    if selection is not None:
        values["principals_document"] = json.dumps([{"credential": values["control_credential"],
            "subject_id": private["installer"]["subject_id"], "kind": "operator", "workspace_grants": {}}])
    material = ROOT / "material"
    material.mkdir(mode=0o700)
    files = {}
    for name, value in values.items():
        path = material / name
        path.write_text(value)
        path.chmod(0o400)
        reference = (document["installation"]["control_auth"]["principals_document"]
            if name == "principals_document" else document["installation"]["references"][name])
        files[reference] = name
    index = {"schema": "cpk.root-bootstrap.material.v1", "files": files}
    if selection is not None:
        from control_plane_kit_servers_cpk_server.bootstrap import plan_root_bootstrap
        plan = plan_root_bootstrap(document, driver_image_id=driver)
        policy_path = material / private["policy"]["file"]
        policy_path.write_bytes(policy)
        policy_path.chmod(0o400)
        index.update(schema="cpk.root-bootstrap.material.v2",
            dynamic_workspace={**private, "plan_digest": plan["digest"]})
    (material / "index.json").write_text(json.dumps(index))
    (material / "index.json").chmod(0o400)
    (ROOT / "state").mkdir(mode=0o700)


COMMISSIONING_STAGES = ("imports", "provenance", "plan", "prepare", "decode", "reuse", "complete-plan")
COMMISSIONING_SUCCESS = "root commissioning: actual driver factories and exact reuse PASS"


def report_commissioning_driver_result(completed):
    """Project only a closed, ordered stage prefix; discard all child errors."""
    markers = tuple("commissioning-stage:" + stage for stage in COMMISSIONING_STAGES)
    lines = completed.stdout.strip().splitlines()
    if completed.returncode == 0 and lines == [*markers, COMMISSIONING_SUCCESS]:
        print(COMMISSIONING_SUCCESS, flush=True)
        return
    stage = "unknown"
    if 0 < len(lines) <= len(markers) and tuple(lines) == markers[:len(lines)]:
        stage = COMMISSIONING_STAGES[len(lines) - 1]
    raise AssertionError("root commissioning actual driver witness failed; stage=" + stage)


def commissioning_driver_witness(run):
    """Use image-owned modules in the actual driver, not the full unit image."""
    # test.sh supplies /source for its fixture entrypoint. The subprocess may
    # load product implementations only from the driver's copied /app paths.
    environment = dict(os.environ)
    environment["PYTHONPATH"] = ":".join("/app/products/" + name + "/src"
        for name in ("cpk_server", "cpk_local_gateway", "secrets_server", "postgres_server"))
    with TemporaryDirectory(prefix="commissioning-fixture-", dir=ROOT) as directory:
        state = Path(directory)
        document = {"schema": "cpk.root-commissioning.intent.v1", "installation_id": run,
            "workspace_id": run, "profile": "operator-offline-read-trust",
            "custody": {"host_directory": str(state), "uid": os.geteuid(), "gid": os.getegid()}}
        # Synthetic immutable ID binds this isolated library witness. It is not
        # image qualification; the existing launcher separately checks its ID.
        selected = json.loads((Path(__file__).resolve().parents[3] / "coordinates/server-products.json").read_text())["upstreams"]
        payload = json.dumps({"intent": document, "preparer": "sha256:" + "a" * 64, "upstreams": selected,
            "bootstrap_input": example_input(installation_id=run, workspace_id=run)})
        program = """
print("commissioning-stage:imports", flush=True)
import importlib, importlib.metadata, json, pathlib, sys
from control_plane_kit_core.configuration import ConfigurationArtifact
from control_plane_kit_secrets.control import decode_secrets_control_configuration
from control_plane_kit_servers_cpk_server.control_configuration import decode_cpk_control_configuration
from control_plane_kit_servers_cpk_server.root_commissioning import plan_root_commissioning, prepare_root_commissioning
print("commissioning-stage:provenance", flush=True)
for name, product in (("control_plane_kit_servers_cpk_server.root_commissioning", "cpk_server"),
                      ("control_plane_kit_servers_secrets_server.configuration", "secrets_server"),
                      ("control_plane_kit_servers_postgres_server.configuration", "postgres_server")):
    loaded = pathlib.Path(importlib.import_module(name).__file__).resolve()
    assert loaded.is_relative_to(pathlib.Path("/app/products") / product / "src")
payload = json.loads(sys.stdin.read())
for name in ("core", "operations", "server_sdk", "interpreters", "secrets"):
    distribution = "control-plane-kit-" + name.replace("_", "-")
    repository = "control-plane-kit" if name in ("core", "operations") else distribution
    selected = payload["upstreams"]["control_plane_kit_" + name + "_commit"]
    direct = json.loads(importlib.metadata.distribution(distribution).read_text("direct_url.json"))
    assert direct["url"] == f"https://github.com/OpenJ92/{repository}/archive/{selected}.zip"
    assert direct.get("subdirectory") == (distribution if name in ("core", "operations") else None)
print("commissioning-stage:plan", flush=True)
plan = plan_root_commissioning(payload["intent"], preparer_image_id=payload["preparer"])
state = pathlib.Path(payload["intent"]["custody"]["host_directory"])
print("commissioning-stage:prepare", flush=True)
result = prepare_root_commissioning(plan, expected_digest=plan["digest"],
    preparer_image_id=payload["preparer"], state_directory=state)
print("commissioning-stage:decode", flush=True)
assert set(result["artifacts"]) == {"cpk", "secrets"}
for role, decode in (("cpk", decode_cpk_control_configuration), ("secrets", decode_secrets_control_configuration)):
    artifact = ConfigurationArtifact.from_descriptor(result["artifacts"][role])
    configured = decode(artifact.content.encode())
    assert configured.target.receiver_id == result["receiver_ids"][role]
    assert {family.purpose.value for family in configured.verifiers} == {
        "workload-node-control-surface-read", "workload-node-health-read"}
print("commissioning-stage:reuse", flush=True)
assert prepare_root_commissioning(plan, expected_digest=plan["digest"],
    preparer_image_id=payload["preparer"], state_directory=state) == result
assert "PRIVATE KEY" not in json.dumps(result)
print("commissioning-stage:complete-plan", flush=True)
from dataclasses import replace
from control_plane_kit_core.products import OciImageReference, ProductDescriptorCodec
from control_plane_kit_core.topology import GraphDescriptorCodec
from control_plane_kit_servers_cpk_server.bootstrap import plan_root_bootstrap
from control_plane_kit_servers_cpk_server.control_configuration import CpkSourceVariant, cpk_source_runtime_contract
from control_plane_kit_servers_secrets_server.configuration import secrets_source_runtime_contract
from control_plane_kit_servers_postgres_server.configuration import (
    postgres_control_configuration_artifact, postgres_control_declaration, postgres_source_runtime_contract)
document = payload["bootstrap_input"]
codec = ProductDescriptorCodec()
for role in ("cpk", "secrets"):
    artifact = ConfigurationArtifact.from_descriptor(result["artifacts"][role])
    contract = (cpk_source_runtime_contract(CpkSourceVariant.DOCKER_CLOUDFLARE, artifact)
        if role == "cpk" else secrets_source_runtime_contract(artifact))
    selected = codec.decode_document(document["installation"]["products"][role])
    document["installation"]["products"][role] = json.loads(codec.encode_document(
        replace(selected.product, runtime_contract=contract)).content)
# Public-only authoring for a third, explicitly supplied fixture receiver. The
# original two-role commissioning result and its exact reuse remain unchanged.
import control_plane_kit_core as core
cpk = decode_cpk_control_configuration(result["artifacts"]["cpk"]["content"].encode())
roles = core.NodeControlGraphReferenceRole
postgres = replace(cpk, target=replace(cpk.target,
    node_id=core.NodeControlGraphReference(roles.NODE, document["installation"]["installation_id"] + "-postgres"),
    provider_socket_name=core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "management"),
    receiver_id="f" * 32), declaration=postgres_control_declaration())
postgres_artifact = postgres_control_configuration_artifact(postgres)
selected = codec.decode_document(document["installation"]["products"]["postgres"])
document["installation"]["products"]["postgres"] = json.loads(codec.encode_document(replace(selected.product,
    image=OciImageReference("example.invalid", "fixture/managed-postgres", "sha256:" + "e" * 64),
    runtime_contract=postgres_source_runtime_contract(postgres_artifact))).content)
document["installation"]["website"] = {
    "image": OciImageReference("example.invalid", "fixture/website", "sha256:" + "a" * 64).descriptor(),
    "external_endpoint": "https://web.example.test", "host_binding": {"address": "127.0.0.1", "port": 18081}}
complete = plan_root_bootstrap(document, driver_image_id=payload["preparer"])
assert len(GraphDescriptorCodec().decode(complete["graph"]).nodes) == 4
assert len(complete["host_bindings"]) == 2
assert len(complete["setup_products"]) == 4
assert complete["setup_routes"].count("command.product.import") == 4
for role in ("cpk", "secrets"):
    node = next(node for node in complete["resources"]["nodes"] if node["node_id"] == document["installation"]["installation_id"] + "-" + role)
    assert node["configuration_files"][0]["artifact"] == result["artifacts"][role]
postgres_node = next(node for node in complete["resources"]["nodes"]
    if node["node_id"] == document["installation"]["installation_id"] + "-postgres")
assert postgres_node["configuration_files"][0]["artifact"] == postgres_artifact.descriptor()
assert postgres_node["secret_files"][0]["target"] == "/run/secrets/postgres/password"
assert not any(binding["node_id"] == postgres_node["node_id"] for binding in complete["host_bindings"])
for name in ("control_plane_kit_servers_cpk_server.bootstrap", "control_plane_kit_servers_cpk_server.client.frontend"):
    assert pathlib.Path(importlib.import_module(name).__file__).resolve().is_relative_to(pathlib.Path("/app/products/cpk_server/src"))
print("root commissioning: actual driver factories and exact reuse PASS")
"""
        completed = subprocess.run([sys.executable, "-c", program], input=payload,
            text=True, capture_output=True, env=environment, cwd="/app", check=False)
        # Do not print arbitrary child exceptions or private fixture payloads.
        report_commissioning_driver_result(completed)
        print("root bootstrap: actual driver complete plan PASS", flush=True)


def initialization_progress_storage_witness(engine, plan, run, uid):
    """Real stopped-container archive lifecycle, without any database effects."""
    import docker
    from control_plane_kit_servers_cpk_server.bootstrap_initialization import (
        PROGRESS_SCHEMA, package_correlation,
    )
    from control_plane_kit_servers_cpk_server.bootstrap_initialization_runtime import (
        _progress, prepare_progress_directory, progress_mount,
    )
    from control_plane_kit_servers_cpk_server.bootstrap_runtime import _save

    target = {"installation_id": run, **package_correlation()}
    labels = {"org.openj92.cpk.test-run": run, "org.openj92.cpk.test-purpose": "initialization-progress"}
    program = '''
import json, sys
from pathlib import Path
from control_plane_kit_servers_cpk_server.bootstrap_initialization import PROGRESS_PATH, _checkpoint
directory = Path(PROGRESS_PATH).parent
directory.mkdir(mode=0o700, exist_ok=False)
_checkpoint(directory, json.loads(sys.argv[1]))
raise SystemExit(int(sys.argv[2]))
'''
    for case, exit_code in (("complete", 0), ("partial", 7)):
        name = run + "-initialization-progress-" + case
        assert not engine.containers.list(all=True, filters={"name": "^/" + name + "$"})
        assert not engine.volumes.list(filters={"name": name})
        state = ROOT / ("initialization-progress-" + case)
        state.mkdir(mode=0o700)
        record = {"engine_id": engine.info()["ID"], "labels": labels,
            "pending": "create-volume", "volume_id": None, "helper_id": None, "observation": None}
        _save(state, record)
        volume = engine.volumes.create(name=name, labels=labels)
        record.update(volume_id=volume.id, pending=None)
        _save(state, record)
        assert volume.id == name and volume.attrs["Labels"] == labels
        progress = {"schema": PROGRESS_SCHEMA, "plan_digest": plan["digest"], **target,
            "schema_acknowledged": True, "initialization": "matching" if exit_code == 0 else "unknown",
            "occurred_at": "2026-10-28T12:00:00Z" if exit_code == 0 else None,
            "pending": None if exit_code == 0 else "initialization"}
        record["pending"] = "create-helper"
        _save(state, record)
        helper = engine.containers.create(plan["driver_image_id"], name=name, user=str(uid), labels=labels,
            command=["python", "-c", program, json.dumps(progress), str(exit_code)],
            network_mode="none", read_only=True, mounts=[progress_mount(volume.id)],
            tmpfs={"/tmp": "rw,noexec,nosuid,size=1m,mode=1777"}, cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}))
        record.update(helper_id=helper.id, pending="prepare-progress")
        _save(state, record)
        helper.reload()
        assert helper.attrs["Image"] == plan["driver_image_id"] and not helper.attrs["State"]["Running"]
        assert all(helper.attrs["Config"]["Labels"].get(key) == value for key, value in labels.items())
        prepare_progress_directory(helper, uid)
        record["pending"] = "start-and-read"
        _save(state, record)
        helper.start()
        assert helper.wait(timeout=30)["StatusCode"] == exit_code, "progress writer failed"
        helper.reload()
        assert helper.attrs["State"]["Running"] is False
        observed = _progress(helper, plan, target, uid)
        assert observed == progress, "stopped helper lost progress"
        record.update(observation=observed, pending=None)
        _save(state, record)
        # Failed-exit evidence remains readable until this fixture explicitly
        # cleans its known resources; production retains them on failure.
        assert _progress(helper, plan, target, uid) == observed
        record["pending"] = "remove-helper"
        _save(state, record)
        helper.reload()
        assert helper.id == record["helper_id"] and helper.attrs["State"]["Running"] is False
        assert all(helper.attrs["Config"]["Labels"].get(key) == value for key, value in labels.items())
        helper.remove()
        helper_absent = False
        try:
            engine.containers.get(record["helper_id"])
        except docker.errors.NotFound:
            helper_absent = True
        assert helper_absent, "progress helper removal unverified"
        record["pending"] = "remove-volume"
        _save(state, record)
        volume = engine.volumes.get(record["volume_id"])
        assert volume.id == name and volume.attrs["Labels"] == labels
        volume.remove()
        volume_absent = False
        try:
            engine.volumes.get(record["volume_id"])
        except docker.errors.NotFound:
            volume_absent = True
        assert volume_absent, "progress volume removal unverified"
        record.update(pending=None, cleanup="complete")
        _save(state, record)
    print("root bootstrap: stopped-helper progress and partial acknowledgement retention PASS", flush=True)


def check(run):
    import docker
    from control_plane_kit_interpreters.docker import DockerSdkClient

    result = json.loads((ROOT / "result.json").read_text())
    assert result["status"] == "local-ready" and result["external_endpoint"] == "unverified"
    receipt = result["receipt"]
    assert receipt["phase"] == "complete" and receipt["pending"] is None
    assert receipt["labels"]["org.openj92.cpk.installation"] == run
    setup = receipt["observations"]["public_setup"]
    assert setup["status"] == "authenticated-local-setup" and setup["workspace_id"] == run
    assert len([item for item in setup["commands"] if item["route"] == "command.product.import"]) == 3
    assert {"read.workspace", "read.current-graph", "read.desired-graph"} <= set(setup["reads"])
    engine = docker.from_env()
    sdk = DockerSdkClient(client=engine)
    plan = json.loads((ROOT / "plan.json").read_text())
    try:
        engine_matches = engine.info()["ID"] == receipt["engine_id"]
        assert engine_matches
        progress_uid = sdk.inspect_image(receipt["observations"]["images"][plan["cpk_node_id"]]).secret_file_owner_uid()
        assert type(progress_uid) is int and progress_uid > 0
        initialization_progress_storage_witness(engine, plan, run, progress_uid)
        for node in plan["resources"]["nodes"]:
            container = engine.containers.get(receipt["resources"]["containers"][node["node_id"]]["id"])
            image = sdk.inspect_image(node["image"])
            assert image is not None and matches_image_reference(node["image"], image.repo_digests)
            assert container.attrs["Image"] == image.image_id and container.attrs["State"]["Running"]
            if (ROOT / "artifact-selection.json").exists() and node["node_id"] in (
                    plan["cpk_node_id"], plan["input"]["installation"]["installation_id"] + "-secrets"):
                from scripts.root_artifact_inputs import qualify_root_artifact, require_root_artifact_process_uid
                selection = json.loads((ROOT / "artifact-selection.json").read_bytes())
                role = "cpk-server" if node["node_id"] == plan["cpk_node_id"] else "secrets-server"
                assert node["image"] == selection["images"][role]
                qualify_root_artifact(role=role, reference=node["image"], source_revision=selection["source_revision"],
                    image_attrs=engine.images.get(node["image"]).attrs, expected_execution_id=container.attrs["Image"])
                process = container.exec_run(["python", "-B", "-c",
                    'import sys; f=open("/proc/1/status","rb"); sys.stdout.buffer.write(f.read(65537))'])
                assert process.exit_code == 0 and len(process.output) <= 65536
                require_root_artifact_process_uid(role=role, pid1_status=process.output.decode("ascii"))
            inspection = sdk.inspect_container(container.id)
            assert inspection is not None
            if node["node_id"] == plan["cpk_node_id"]:
                from control_plane_kit_interpreters.docker.authority import (
                    DockerAuthorityConformance, docker_authority_conformance,
                )
                from control_plane_kit_interpreters.docker.sdk import DockerSdkBindMount
                retain_authority_evidence(run, container, inspection, node, receipt, engine_matches)
                binds = inspection.bind_mounts
                known = isinstance(binds, tuple)
                print(json.dumps({"cpk_authority_mount_diagnostic": {
                    "expected": {"count": 1, "source_is_canonical": True,
                                 "target_is_canonical": True, "read_only": False},
                    "observed": {"known": known, "count": len(binds) if known else None,
                        "truncated": known and len(binds) > 4,
                        "mounts": [{"source_is_canonical": mount.source_path == "/var/run/docker.sock",
                                    "target_is_canonical": mount.target_path == "/var/run/docker.sock",
                                    "read_only": mount.read_only if type(mount.read_only) is bool else "unknown"}
                                   for mount in (binds[:4] if known else ())]}}}), flush=True)
                socket_group = str(os.stat("/var/run/docker.sock").st_gid)
                assert docker_authority_conformance(
                    inspection, expected_mounts=(DockerSdkBindMount(
                        source_path="/var/run/docker.sock", target_path="/var/run/docker.sock"),),
                    expected_groups=(socket_group,), client=sdk,
                ) is DockerAuthorityConformance.CONFORMANT
                assert inspection.supplementary_groups == (socket_group,)
                assert image.configured_user == "10001"
                verify_numeric_socket_read(container, socket_group, receipt["engine_id"], node["image"])
            else:
                assert inspection.bind_mounts == ()
                assert inspection.supplementary_groups == ()
            assert {(entry.target_path, entry.volume_name) for entry in inspection.readonly_secret_mounts} == {
                (entry["target"], entry["name"]) for entry in
                (*node["secret_files"], *node["configuration_files"], *node.get("installer_files", []))}
            for entry in (*node["secret_files"], *node.get("installer_files", [])):
                assert receipt["observations"]["protected_files"][entry["name"]] == {
                    "uid": image.secret_file_owner_uid(), "mode": "0400", "verified": True}
            for entry in node["configuration_files"]:
                assert entry["name"] in receipt["resources"]["volumes"]
                expected = {"path": entry["target"], "sha256": entry["sha256"],
                    "uid": image.secret_file_owner_uid(), "mode": int(entry["artifact"]["file_mode"], 8)}
                probe = '''
import hashlib, json, os, stat
from pathlib import Path
path = Path(EXPECTED["path"])
metadata = path.stat()
assert os.geteuid() == EXPECTED["uid"] and os.geteuid() != 0
assert stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 0
assert stat.S_IMODE(metadata.st_mode) == EXPECTED["mode"] == 0o444
with path.open("rb") as stream:
    raw = stream.read(4097)
assert len(raw) <= 4096 and hashlib.sha256(raw).hexdigest() == EXPECTED["sha256"]
try:
    with path.open("ab") as stream:
        stream.write(b"unexpected-write")
except OSError:
    denied = True
else:
    denied = False
assert denied
print(json.dumps({"numeric_read": True, "mode": True, "bytes": True, "write_denied": True}))
'''
                result = container.exec_run(["python", "-I", "-c", "EXPECTED=" + repr(expected) + "\n" + probe])
                assert result.exit_code == 0 and len(result.output) <= 256, "configuration numeric recipient witness failed"
                assert json.loads(result.output) == {"numeric_read": True, "mode": True, "bytes": True, "write_denied": True}
            for value_path in (ROOT / "material").iterdir():
                if value_path.name != "index.json":
                    assert value_path.read_bytes() not in container.logs(tail=1000), "secret in product logs"
        cpk = engine.containers.get(receipt["resources"]["containers"][plan["cpk_node_id"]]["id"])
        # The real product's existing public client proves authentication denial.
        probe = '''
from pathlib import Path
import tempfile
from control_plane_kit_servers_cpk_server.client.profile import ClientProfile
from control_plane_kit_servers_cpk_server.client.transport import PublicHttpTransport, ClientAuthorizationError
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'credential'
    path.write_text('deliberately-invalid-root-witness-token')
    path.chmod(0o400)
    profile = ClientProfile('http://127.0.0.1:8080', WORKSPACE,
        {role: path for role in ('operator', 'approver', 'worker')}, Path(directory))
    try:
        PublicHttpTransport(profile).call('read.workspace', path_parameters={'workspace_id': WORKSPACE},
                                         payload={}, credential_role='operator')
    except ClientAuthorizationError:
        pass
    else:
        raise AssertionError('wrong credential accepted')
'''
        outcome = cpk.exec_run(["python", "-c", "WORKSPACE=" + repr(run) + "\n" + probe])
        assert outcome.exit_code == 0, "wrong-credential witness failed"
        if plan["input"]["installation"].get("workspace_authority", {}).get("mode") == "dynamic-v1":
            dynamic_restart_witness(engine, cpk, plan, receipt)
        before = (ROOT / "state" / "receipt.json").read_bytes()
        (ROOT / "receipt-before").write_bytes(before)
        print("root bootstrap: real launcher, canonical images, numeric delivery, public setup, denial PASS; external unverified")
    finally:
        engine.close()


def dynamic_restart_witness(engine, cpk, plan, receipt):
    """Public revocation and actual retained process restart, without reseeding."""
    import docker
    from control_plane_kit_servers_cpk_server.bootstrap_runtime import _material

    _, intent = _material(plan, ROOT / "material" / "index.json")
    initialized = receipt["observations"]["initialization"]
    assert initialized["schema_acknowledged"] and initialized["initialization"] == "matching"
    assert initialized["pending"] is None
    helper = receipt["initialization_helper"]
    assert helper["cleanup"] == "complete" and helper["helper_removed"]
    assert receipt["setup_helper_removed"]
    for identity in (helper["helper_id"], receipt["setup_helper_id"]):
        absent = False
        try:
            engine.containers.get(identity)
        except docker.errors.NotFound:
            absent = True
        assert absent, "completed dynamic helper remains"
    for value in (*helper["temporary_volumes"].values(),
                  *receipt["observations"]["removed_setup_volumes"].values()):
        assert value["removed"]
        absent = False
        try:
            engine.volumes.get(value["id"])
        except docker.errors.NotFound:
            absent = True
        assert absent, "completed dynamic helper input remains"
    node = next(value for value in plan["resources"]["nodes"] if value["node_id"] == plan["cpk_node_id"])
    policy, = node["installer_files"]
    expected = {"workspace": plan["input"]["installation"]["workspace_id"],
        "runtime": plan["input"]["installation"]["installation_id"] + "-docker",
        "authority": plan["input"]["installation"]["runtime_authority"],
        "policy_path": policy["target"], "policy_sha256": hashlib.sha256(intent.policy_bytes).hexdigest()}
    program = '''
import hashlib, json, os, stat, tempfile, time
from pathlib import Path
from control_plane_kit_servers_cpk_server.client.profile import ClientProfile
from control_plane_kit_servers_cpk_server.client.transport import PublicHttpTransport, ClientAuthorizationError, ClientTransportError
def main():
    path = Path(EXPECTED["policy_path"])
    metadata = path.stat()
    assert os.geteuid() == metadata.st_uid == 10001 and stat.S_IMODE(metadata.st_mode) == 0o400
    with path.open("rb") as stream:
        raw = stream.read(65537)
    assert len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == EXPECTED["policy_sha256"]
    policy = json.loads(raw)
    try:
        with path.open("ab") as stream:
            stream.write(b"unexpected-write")
    except OSError:
        pass
    else:
        raise AssertionError("policy write permitted")
    target, = policy["administrators"]
    principal, = json.loads(os.environ["CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"])
    assert principal["subject_id"] == target["subject_id"]
    with tempfile.TemporaryDirectory() as directory:
        credential = Path(directory) / "credential"
        credential.write_text(principal["credential"])
        credential.chmod(0o400)
        profile = ClientProfile("http://127.0.0.1:8080", EXPECTED["workspace"],
            {role: credential for role in ("operator", "approver", "worker")}, Path(directory))
        transport = PublicHttpTransport(profile, timeout_seconds=3)
        def call(route, payload, **coordinates):
            return transport.call(route, path_parameters={"workspace_id": EXPECTED["workspace"], **coordinates},
                payload=payload, credential_role="operator")
        # Readiness retries are reads only; every mutation below is sent once.
        for attempt in range(30):
            try:
                permission = call("read.workspace-permission", {"target": target})
                break
            except ClientTransportError:
                if attempt == 29:
                    raise
                time.sleep(1)
        query = {"runtime_id": EXPECTED["runtime"], "authority_ref": EXPECTED["authority"]}
        assignment = call("read.managed-runtime-assignment", query)
        if MODE == "revoke":
            authority = call("read.runtime-authority-detail", {}, authority_ref=EXPECTED["authority"])["runtime_authority"]
            assert assignment["registration_id"] == authority["registration_id"]
            assert assignment["status"] == "active" and permission["scopes"]
            call("read.current-graph", {})
            call("command.workspace-permission.revoke", {"target": target,
                "scopes": permission["scopes"], "expected_revision": permission["revision"],
                "idempotency_key": "fixture-revoke-ordinary"})
            call("command.managed-runtime-access.revoke", {**query,
                "expected_revision": assignment["revision"], "idempotency_key": "fixture-revoke-management"})
        else:
            assert permission["scopes"] == [] and assignment["status"] == "revoked"
            try:
                call("read.current-graph", {})
            except ClientAuthorizationError:
                pass
            else:
                raise AssertionError("ordinary access restored")
        return {"permission_revision": permission["revision"], "management_revision": assignment["revision"],
            "registration_sha256": hashlib.sha256(assignment["registration_id"].encode()).hexdigest()}
try:
    result = main()
except Exception:
    raise SystemExit(1) from None
print(json.dumps(result, sort_keys=True))
'''
    def observe(mode):
        result = cpk.exec_run(["python", "-B", "-c",
            "EXPECTED=" + repr(expected) + "\nMODE=" + repr(mode) + "\n" + program])
        assert result.exit_code == 0 and len(result.output) <= 512, "dynamic public restart witness failed"
        value = json.loads(result.output)
        assert set(value) == {"permission_revision", "management_revision", "registration_sha256"}
        assert all(type(value[key]) is int and value[key] >= 0 for key in ("permission_revision", "management_revision"))
        return value

    before = observe("revoke")
    cpk.reload()
    assert cpk.id == receipt["resources"]["containers"][plan["cpk_node_id"]]["id"]
    assert cpk.attrs["Image"] == receipt["observations"]["images"][plan["cpk_node_id"]]
    assert all(cpk.attrs["Config"]["Labels"].get(key) == value for key, value in receipt["labels"].items())
    mounts = cpk.attrs["Mounts"]
    started = cpk.attrs["State"]["StartedAt"]
    cpk.restart(timeout=20)
    cpk.reload()
    assert cpk.attrs["State"]["Running"] and cpk.attrs["State"]["StartedAt"] != started
    assert cpk.attrs["Mounts"] == mounts
    after = observe("verify")
    assert after == {**before, "permission_revision": before["permission_revision"] + 1,
        "management_revision": before["management_revision"] + 1}
    print("dynamic root launcher: private custody, public revocation and retained process restart PASS", flush=True)


def verify_numeric_socket_read(container, socket_group, engine_id, image_reference):
    """One read as the image's configured user; no user or group override.

    Candidate review seals the complete image account baseline before release.
    Image account data supplies expected identity, never process observations.
    """
    baseline = reviewed_image_account(image_reference)
    expected_groups = baseline.expected_groups(image_reference, int(socket_group))
    probe = '''
import hashlib, http.client, io, json, os, pwd, signal, socket, stat, time

def timed_out(*args):
    raise TimeoutError()

class CapturedResponse:
    def __init__(self, data):
        self.data = data

    def makefile(self, *args):
        return io.BytesIO(self.data)

phase = "account-uid"
membership = None
try:
    signal.signal(signal.SIGALRM, timed_out)
    deadline = time.monotonic() + 10
    signal.setitimer(signal.ITIMER_REAL, 10)
    account = pwd.getpwnam("cpk")
    assert account.pw_uid == EXPECTED_UID and os.geteuid() == EXPECTED_UID
    phase = "primary-gid"
    assert account.pw_gid == EXPECTED_PRIMARY_GID and os.getegid() == EXPECTED_PRIMARY_GID
    phase = "groups"
    groups_match, membership = numeric_group_check(
        os.getegid(), os.getgroups(), EXPECTED_GROUPS, EXPECTED_SOCKET_GID)
    assert groups_match
    phase = "socket-type"
    assert stat.S_ISSOCK(os.stat("/var/run/docker.sock").st_mode)
    phase = "connect"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        remaining = min(5, deadline - time.monotonic())
        assert remaining > 0
        signal.setitimer(signal.ITIMER_REAL, remaining)
        connection.connect("/var/run/docker.sock")
        connection.sendall(b"GET /info HTTP/1.1\\r\\nHost: docker\\r\\nConnection: close\\r\\n\\r\\n")
        phase = "receive"
        captured = bytearray()
        while True:
            chunk = connection.recv(min(4096, 65537 - len(captured)))
            if not chunk:
                break
            captured.extend(chunk)
            assert len(captured) <= 65536
        # Cap the complete wire response, including headers, before parsing.
        phase = "http-parse"
        response = http.client.HTTPResponse(CapturedResponse(captured))
        response.begin()
        body = response.read(65537)
        phase = "http-status"
        assert response.status == 200 and len(body) <= 65536
        phase = "schema"
        observed = json.loads(body)
        assert type(observed) is dict and type(observed.get("ID")) is str
        phase = "correlation"
        assert hashlib.sha256(observed["ID"].encode()).hexdigest() == EXPECTED_ENGINE_DIGEST
    signal.setitimer(signal.ITIMER_REAL, 0)
    print(json.dumps({"numeric_identity": True, "effective_groups": True,
                      "socket_type": True, "bounded_read": True, "provider_correlated": True}))
except Exception as error:
    # Never print provider exceptions, raw responses, identities or paths.
    signal.setitimer(signal.ITIMER_REAL, 0)
    reason = ("timeout" if isinstance(error, TimeoutError) else
              "assertion" if isinstance(error, AssertionError) else "operation-error")
    print(json.dumps({"schema": "cpk.numeric-probe.failure.v2", "phase": phase,
                      "reason": reason, "membership": membership
                      if phase == "groups" and reason == "assertion" else None}))
    raise SystemExit(1)
'''
    source = (inspect.getsource(numeric_group_check)
              + "EXPECTED_UID=" + repr(baseline.uid) + "\n"
              + "EXPECTED_PRIMARY_GID=" + repr(baseline.primary_gid) + "\n"
              + "EXPECTED_GROUPS=" + repr(tuple(sorted(expected_groups))) + "\n"
              + "EXPECTED_SOCKET_GID=" + repr(int(socket_group)) + "\n"
              + "EXPECTED_ENGINE_DIGEST=" + repr(hashlib.sha256(engine_id.encode()).hexdigest()) + "\n" + probe)
    class ProbeDeadline(BaseException):
        """Escape SDK exception/retry handling when the controller deadline fires."""

    def deadline_expired(*args):
        raise ProbeDeadline()

    # This owning Linux witness runs on the main thread. Bound the complete SDK
    # call, including exec creation/start/inspection, not only the child socket.
    previous_handler = signal.signal(signal.SIGALRM, deadline_expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, 10)
        outcome = container.exec_run(["python", "-I", "-c", source])
    except (ProbeDeadline, Exception):
        raise AssertionError("numeric CPK probe unavailable or timed out") from None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    if type(outcome.output) is not bytes or len(outcome.output) > 512:
        raise AssertionError("numeric CPK probe output unavailable or exceeded bound")
    if outcome.exit_code != 0:
        try:
            failure = json.loads(outcome.output)
        except (ValueError, UnicodeError):
            raise AssertionError("numeric CPK probe failure classification unavailable") from None
        phases = {"account-uid", "primary-gid", "groups", "socket-type", "connect",
                  "receive", "http-parse", "http-status", "schema", "correlation"}
        reasons = {"assertion", "timeout", "operation-error"}
        if (type(failure) is not dict or set(failure) != {"schema", "phase", "reason", "membership"}
                or failure["schema"] != "cpk.numeric-probe.failure.v2"
                or type(failure["phase"]) is not str or failure["phase"] not in phases
                or type(failure["reason"]) is not str or failure["reason"] not in reasons):
            raise AssertionError("numeric CPK probe failure classification unavailable")
        detail = ""
        membership = failure["membership"]
        if failure["phase"] == "groups" and failure["reason"] == "assertion":
            keys = ("declared_socket_group_present", "unexpected_groups_present")
            if (type(membership) is not dict or set(membership) != set(keys)
                    or any(type(membership[key]) is not bool for key in keys)):
                raise AssertionError("numeric CPK probe failure classification unavailable")
            detail = "; " + ", ".join(key + "=" + str(membership[key]).lower() for key in keys)
        elif membership is not None:
            raise AssertionError("numeric CPK probe failure classification unavailable")
        raise AssertionError("numeric CPK probe failed: " + failure["phase"] + "/" + failure["reason"] + detail)
    assert json.loads(outcome.output) == {
        "numeric_identity": True, "effective_groups": True, "socket_type": True,
        "bounded_read": True, "provider_correlated": True,
    }
    print("root bootstrap: numeric CPK identity, socket read and provider correlation PASS; mutation permission unverified")


def cleanup(run):
    import docker
    engine = docker.from_env()
    try:
        path = ROOT / "state" / "receipt.json"
        if not path.exists():
            return
        receipt = json.loads(path.read_text())
        assert receipt["engine_id"] == engine.info()["ID"]
        assert receipt["labels"]["org.openj92.cpk.installation"] == run
        # Pending effects may have unrecorded resources. Preserve them for review.
        assert receipt["phase"] == "complete" and receipt["pending"] is None, "uncertain root acquisition; cleanup held"
        for kind in ("containers", "volumes", "networks"):
            collection = getattr(engine, kind)
            for item in receipt["resources"][kind].values():
                resource = collection.get(item["id"])
                labels = resource.attrs.get("Config", {}).get("Labels", {}) if kind == "containers" else resource.attrs["Labels"]
                assert all(labels.get(key) == value for key, value in receipt["labels"].items())
                if kind == "containers":
                    resource.remove(force=True)
                else:
                    resource.remove()
                absent = False
                try:
                    collection.get(item["id"])
                except docker.errors.NotFound:
                    absent = True
                assert absent, "owned resource remains"
        print("root bootstrap: exact owned resource cleanup PASS")
    finally:
        engine.close()


def initialization_after_restart(run):
    result = json.loads((ROOT / "initialization-after.json").read_bytes())
    original = json.loads((ROOT / "result.json").read_bytes())["receipt"]
    assert result["status"] == "observed-initialization"
    receipt = result["receipt"]
    assert receipt["labels"]["org.openj92.cpk.installation"] == run
    assert receipt["resources"] == original["resources"]
    assert receipt["observations"] == original["observations"]
    inspection = receipt["initialization_inspection"]
    assert inspection["pending"] is None and inspection["cleanup"] == "complete" and inspection["helper_removed"]
    assert all(value["removed"] for value in inspection["temporary_volumes"].values())
    observed = inspection["observation"]
    initialized = original["observations"]["initialization"]
    assert observed["initialization"] == "matching" and observed["pending"] is None
    for key in ("plan_digest", "installation_id", "operations_commit", "schema_sha256", "occurred_at"):
        assert observed[key] == initialized[key]
    saved = (ROOT / "state" / "receipt.json").read_bytes()
    assert json.loads(saved) == receipt
    (ROOT / "receipt-before").write_bytes(saved)
    print("dynamic root launcher: retained initialization binding inspection PASS", flush=True)


def cleanup_private(run):
    """Successful fixture cleanup removes only its two secret-bearing trees."""
    import shutil
    receipt = json.loads((ROOT / "state" / "receipt.json").read_bytes())
    assert receipt["labels"]["org.openj92.cpk.installation"] == run
    assert receipt["phase"] == "complete" and receipt["pending"] is None
    directories = (ROOT / "material", ROOT / "commissioning")
    for directory in directories:
        assert directory.is_dir() and not directory.is_symlink()
        for entry in directory.rglob("*"):
            assert not entry.is_symlink() and (entry.is_file() or entry.is_dir())
    for directory in directories:
        shutil.rmtree(directory)
        assert not directory.exists()
    print("dynamic root launcher: owned credential and commissioning private-file cleanup PASS", flush=True)


if __name__ == "__main__":
    action, run = sys.argv[1:]
    if action == "prepare":
        prepare(run)
    elif action == "check":
        check(run)
    elif action == "cleanup":
        cleanup(run)
    elif action == "initialization-after":
        initialization_after_restart(run)
    elif action == "cleanup-private":
        cleanup_private(run)
    elif action == "digest":
        print(json.loads((ROOT / "plan.json").read_text())["digest"])
    elif action == "unchanged":
        assert (ROOT / "receipt-before").read_bytes() == (ROOT / "state" / "receipt.json").read_bytes()
    else:
        raise SystemExit(2)
