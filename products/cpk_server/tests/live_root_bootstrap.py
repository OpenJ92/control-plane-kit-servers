"""Owning gate fixture and exact-ID cleanup for the real bootstrap.sh witness."""

import base64
import json
import os
from pathlib import Path
import secrets
import sys

from products.cpk_server.examples.root_bootstrap_input import example_input
from control_plane_kit_servers_cpk_server.bootstrap import matches_image_reference


ROOT = Path("/witness")


def prepare(run):
    os.umask(0o077)
    port_text = os.environ.get("CPK_ROOT_TEST_PORT", "18089")
    if not port_text.isascii() or not port_text.isdecimal() or not 1 <= int(port_text) <= 65535:
        raise ValueError("CPK_ROOT_TEST_PORT must be an integer from 1 to 65535")
    document = example_input(installation_id=run, workspace_id=run, port=int(port_text))
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
    material = ROOT / "material"
    material.mkdir(mode=0o700)
    files = {}
    for name, value in values.items():
        path = material / name
        path.write_text(value)
        path.chmod(0o400)
        files[document["installation"]["references"][name]] = name
    (material / "index.json").write_text(json.dumps({"schema": "cpk.root-bootstrap.material.v1", "files": files}))
    (material / "index.json").chmod(0o400)
    (ROOT / "state").mkdir(mode=0o700)


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
        assert engine.info()["ID"] == receipt["engine_id"]
        for node in plan["resources"]["nodes"]:
            container = engine.containers.get(receipt["resources"]["containers"][node["node_id"]]["id"])
            image = sdk.inspect_image(node["image"])
            assert image is not None and matches_image_reference(node["image"], image.repo_digests)
            assert container.attrs["Image"] == image.image_id and container.attrs["State"]["Running"]
            inspection = sdk.inspect_container(container.id)
            assert inspection is not None
            if node["node_id"] == plan["cpk_node_id"]:
                from control_plane_kit_interpreters.docker.sdk import DockerSdkBindMount
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
                assert inspection.bind_mounts == (DockerSdkBindMount(
                    source_path="/var/run/docker.sock", target_path="/var/run/docker.sock"),)
                assert inspection.supplementary_groups == (str(os.stat("/var/run/docker.sock").st_gid),)
            else:
                assert inspection.bind_mounts == ()
                assert inspection.supplementary_groups == ()
            assert {(entry.target_path, entry.volume_name) for entry in inspection.readonly_secret_mounts} == {
                (entry["target"], entry["name"]) for entry in node["secret_files"]}
            for entry in node["secret_files"]:
                assert receipt["observations"]["protected_files"][entry["name"]] == {
                    "uid": image.secret_file_owner_uid(), "mode": "0400", "verified": True}
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
        before = (ROOT / "state" / "receipt.json").read_bytes()
        (ROOT / "receipt-before").write_bytes(before)
        print("root bootstrap: real launcher, canonical images, numeric delivery, public setup, denial PASS; external unverified")
    finally:
        engine.close()


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


if __name__ == "__main__":
    action, run = sys.argv[1:]
    if action == "prepare":
        prepare(run)
    elif action == "check":
        check(run)
    elif action == "cleanup":
        cleanup(run)
    elif action == "digest":
        print(json.loads((ROOT / "plan.json").read_text())["digest"])
    elif action == "unchanged":
        assert (ROOT / "receipt-before").read_bytes() == (ROOT / "state" / "receipt.json").read_bytes()
    else:
        raise SystemExit(2)
