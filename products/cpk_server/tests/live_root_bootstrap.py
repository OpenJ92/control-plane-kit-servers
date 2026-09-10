"""Owning gate fixture and exact-ID cleanup for the real bootstrap.sh witness."""

import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import stat
import sys

from products.cpk_server.examples.root_bootstrap_input import example_input
from control_plane_kit_servers_cpk_server.bootstrap import matches_image_reference


ROOT = Path("/witness")


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
        engine_matches = engine.info()["ID"] == receipt["engine_id"]
        assert engine_matches
        for node in plan["resources"]["nodes"]:
            container = engine.containers.get(receipt["resources"]["containers"][node["node_id"]]["id"])
            image = sdk.inspect_image(node["image"])
            assert image is not None and matches_image_reference(node["image"], image.repo_digests)
            assert container.attrs["Image"] == image.image_id and container.attrs["State"]["Running"]
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
                verify_numeric_socket_read(container, socket_group, receipt["engine_id"])
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


def verify_numeric_socket_read(container, socket_group, engine_id):
    """One read as the image's configured user; no user or group override.

    Candidate image review must seal the cpk account's UID/GID before releasing
    this witness. Account data supplies expected identity, never probe output.
    """
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
try:
    signal.signal(signal.SIGALRM, timed_out)
    deadline = time.monotonic() + 10
    signal.setitimer(signal.ITIMER_REAL, 10)
    account = pwd.getpwnam("cpk")
    assert account.pw_uid == 10001 and os.geteuid() == account.pw_uid
    phase = "primary-gid"
    assert os.getegid() == account.pw_gid
    phase = "groups"
    assert {os.getegid(), *os.getgroups()} == {account.pw_gid, EXPECTED_SOCKET_GID}
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
    print(json.dumps({"schema": "cpk.numeric-probe.failure.v1", "phase": phase,
                      "reason": reason}))
    raise SystemExit(1)
'''
    source = ("EXPECTED_SOCKET_GID=" + repr(int(socket_group)) + "\n"
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
        if (type(failure) is not dict or set(failure) != {"schema", "phase", "reason"}
                or failure["schema"] != "cpk.numeric-probe.failure.v1"
                or type(failure["phase"]) is not str or failure["phase"] not in phases
                or type(failure["reason"]) is not str or failure["reason"] not in reasons):
            raise AssertionError("numeric CPK probe failure classification unavailable")
        raise AssertionError("numeric CPK probe failed: " + failure["phase"] + "/" + failure["reason"])
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
