"""Owning source-image/SDK bootstrap witness; not parent custody admission."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
from uuid import uuid4

import docker
import httpx

from control_plane_kit_core.secrets import (
    SecretFileMode, SecretProviderEndpointReference, SecretReference,
    SecretUseIntent, SecretValue,
)
from control_plane_kit_interpreters.docker import DockerSdkClient, DockerSdkSecretMount
from control_plane_kit_interpreters.secret_provider import (
    ControlPlaneKitSecretsClient, SecretProviderBootstrapRegistry,
    SecretProviderClientCode, SecretProviderClientError,
)


def exercise_provider(token: str, application_value: str) -> None:
    """Use the existing public provider client and synthetic local credentials."""
    endpoint = SecretProviderEndpointReference("control-plane-kit")
    credential = SecretReference("secret://bootstrap/provider-token")
    reference = SecretReference("secret://control-plane-kit/application/postgres-password")
    request = dict(workspace_id="workspace-numeric-bootstrap", reference=reference,
                   intent=SecretUseIntent.POSTGRES_PASSWORD,
                   caller_subject="numeric-bootstrap-client")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "token"
        path.write_text(token, encoding="ascii")
        path.chmod(0o400)
        registry = SecretProviderBootstrapRegistry(
            endpoints={endpoint: "http://secrets-provider:8081"},
            credential_files={credential: path})
        configuration = registry.configuration_for(
            endpoint_reference=endpoint, credential_reference=credential)
        provider = ControlPlaneKitSecretsClient(configuration)
        written = provider.write(**request, value=SecretValue(application_value),
                                 correlation_id="numeric-bootstrap-write")
        assert written.reference == reference
        resolved = provider.resolve(**request, correlation_id="numeric-bootstrap-resolve")
        assert resolved.value.reveal() == application_value, "provider value mismatch"
        wrong_path = Path(directory) / "wrong-token"
        wrong_path.write_text("deliberately-invalid-local-token", encoding="ascii")
        wrong_path.chmod(0o400)
        denied_registry = SecretProviderBootstrapRegistry(
            endpoints={endpoint: "http://secrets-provider:8081"},
            credential_files={credential: wrong_path})
        denied = ControlPlaneKitSecretsClient(denied_registry.configuration_for(
            endpoint_reference=endpoint, credential_reference=credential))
        try:
            denied.resolve(**request, correlation_id="numeric-bootstrap-denied")
        except SecretProviderClientError as error:
            assert error.code is SecretProviderClientCode.DENIED
            assert token not in repr(error) and application_value not in repr(error)
        else:
            raise AssertionError("provider accepted wrong credentials")


def main() -> None:
    engine = docker.from_env()
    run_id = os.environ["CPK_SECRET_TEST_RUN"]
    image_id = os.environ["CPK_SECRET_PRODUCT_IMAGE"]
    network_id = os.environ["CPK_SECRET_NETWORK"]
    labels = {"org.openj92.cpk.test-run": run_id,
              "org.openj92.project": "control-plane-kit-servers"}
    sdk = DockerSdkClient(client=engine,
                          configuration_helper_image=os.environ["CPK_SECRET_HELPER_IMAGE"])
    resources = []
    helper_ids = []
    absent = set()
    original_helper = sdk._create_configuration_helper

    def tracked_helper(*args, **kwargs):
        helper = original_helper(*args, **kwargs)
        helper_ids.append(helper.id)
        return helper

    sdk._create_configuration_helper = tracked_helper
    token = secrets.token_urlsafe(48)
    root_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    application_value = secrets.token_urlsafe(40)
    credential_document = json.dumps([{
        "subject": "numeric-bootstrap-client", "token": token,
        "grants": [
            {"action": "secret.write", "workspace_id": "workspace-numeric-bootstrap"},
            {"action": "secret.resolve", "workspace_id": "workspace-numeric-bootstrap",
             "intents": ["postgres.password"]},
        ],
    }])
    material = {
        "/run/secrets/cpk-secrets/master.key": root_key,
        "/run/secrets/cpk-secrets/credentials.json": credential_document,
    }
    sensitive = [root_key, token, credential_document, application_value]
    source = None
    cleanup_failed = False
    try:
        assert engine.info().get("ID") == os.environ["CPK_SECRET_ENGINE_ID"], "engine mismatch"
        assert engine.networks.get(network_id).attrs["Labels"] == labels
        assert engine.images.get(image_id).labels.get("org.openj92.cpk.test-run") == run_id
        inspected = sdk.inspect_image(image_id)
        assert inspected is not None and inspected.image_id == image_id
        uid = inspected.secret_file_owner_uid()
        assert uid == 10006, "actual product must declare numeric UID10006"
        mounts = []
        for target, value in material.items():
            volume = engine.volumes.create(name=f"cpk-secret-{uuid4().hex}", labels=labels)
            resources.append((engine.volumes, volume.name))
            sdk.materialize_secret_file(volume.name, SecretValue(value),
                                        SecretFileMode.OWNER_READ_ONLY, owner_uid=uid)
            evidence = sdk.inspect_secret_file(volume.name)
            digest = hashlib.sha256(value.encode()).hexdigest()
            assert evidence.uid == uid and evidence.mode == 0o400 and evidence.regular_file
            assert evidence.content_digest == digest, "delivered content mismatch"
            mounts.append(dict(DockerSdkSecretMount(target, volume.name).docker_mount()))
        data = engine.volumes.create(name=f"cpk-secret-data-{uuid4().hex}", labels=labels)
        resources.append((engine.volumes, data.name))
        source = engine.containers.create(
            image_id, name=f"cpk-secret-provider-{uuid4().hex}", labels=labels,
            mounts=[*mounts, docker.types.Mount("/var/lib/cpk-secrets", data.name, type="volume")],
            network=network_id,
            networking_config={network_id:
                engine.api.create_endpoint_config(aliases=["secrets-provider"])},
            cap_drop=["ALL"], security_opt=["no-new-privileges"],
            log_config=docker.types.LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}))
        resources.append((engine.containers, source.id))
        source.start()
        readiness = "not-observed"
        for _ in range(30):
            source.reload()
            assert source.status == "running", "actual Secrets process exited"
            try:
                response = httpx.get("http://secrets-provider:8081/health/ready", timeout=1, trust_env=False)
                readiness = str(response.status_code)
                if response.status_code == 200:
                    break
            except httpx.TransportError:
                readiness = "transport-unavailable"
            time.sleep(1)
        else:
            raise AssertionError(f"actual Secrets readiness failed: {readiness}")
        source.reload()
        assert source.attrs["Image"] == image_id
        assert source.attrs["Config"]["User"] == "10006"
        assert not source.attrs["HostConfig"]["PortBindings"]
        actual_mounts = {mount["Destination"]: mount for mount in source.attrs["Mounts"]}
        for mount in mounts:
            observed = actual_mounts[mount["Target"]]
            assert observed["Name"] == mount["Source"] and observed["RW"] is False
        expected = {path: hashlib.sha256(value.encode()).hexdigest()
                    for path, value in material.items()}
        probe = f'''
import hashlib, os, pathlib, pwd, stat
account = pwd.getpwnam("secrets")
assert os.getuid() == account.pw_uid == 10006
assert os.getgid() == account.pw_gid
assert os.environ["HOME"] == account.pw_dir
assert os.access(account.pw_dir, os.R_OK | os.X_OK)
status = pathlib.Path("/proc/1/status").read_text()
assert next(line.split()[1:] for line in status.splitlines() if line.startswith("Uid:")) == ["10006"] * 4
assert os.access("/var/lib/cpk-secrets", os.R_OK | os.W_OK | os.X_OK)
for path, digest in {expected!r}.items():
    file = pathlib.Path(path)
    info = file.stat()
    assert stat.S_ISREG(info.st_mode) and info.st_uid == 10006 and stat.S_IMODE(info.st_mode) == 0o400
    assert hashlib.sha256(file.read_bytes()).hexdigest() == digest
    try:
        file.write_bytes(b"forbidden")
    except OSError:
        denied = True
    else:
        raise AssertionError("bootstrap writable")
'''
        result = source.exec_run(["python", "-B", "-c", probe])
        assert not any(value.encode() in result.output for value in sensitive), "probe material leak"
        assert result.exit_code == 0, "actual product UID/account/HOME/file law failed"
        deny_probe = f'''
import os, pathlib
assert os.getuid() == 10007
for path in {list(material)!r}:
    try:
        pathlib.Path(path).read_bytes()
    except PermissionError:
        denied = True
    else:
        raise AssertionError("unrelated UID read bootstrap")
'''
        other = engine.containers.create(
            image_id, name=f"cpk-secret-other-{uuid4().hex}", labels=labels,
            entrypoint=["python", "-B", "-c"], command=[deny_probe], user="10007",
            mounts=mounts, network_mode="none", read_only=True,
            cap_drop=["ALL"], security_opt=["no-new-privileges"])
        resources.append((engine.containers, other.id))
        other.start()
        assert other.wait(timeout=30).get("StatusCode") == 0, "other UID access law failed"
        assert not any(value.encode() in other.logs(tail=30) for value in sensitive)
        exercise_provider(token, application_value)
        logs = source.logs(stdout=True, stderr=True, tail=200)
        assert len(logs) <= 1024 * 1024, "unbounded product logs"
        assert not any(value.encode() in logs for value in sensitive), "provider material leak"
    finally:
        for manager, identity in reversed(resources):
            try:
                resource = manager.get(identity)
                resource.reload()
                observed_labels = resource.attrs.get("Labels") or resource.attrs.get("Config", {}).get("Labels", {})
                if observed_labels.get("org.openj92.cpk.test-run") != run_id:
                    cleanup_failed = True
                    continue
                if isinstance(resource, docker.models.containers.Container):
                    resource.remove(force=True)
                else:
                    resource.remove()
                try:
                    manager.get(identity)
                except docker.errors.NotFound:
                    absent.add((type(manager).__name__, identity))
                else:
                    cleanup_failed = True
            except docker.errors.NotFound:
                absent.add((type(manager).__name__, identity))
            except Exception:
                cleanup_failed = True
        for identity in helper_ids:
            try:
                engine.containers.get(identity)
            except docker.errors.NotFound:
                absent.add((type(engine.containers).__name__, identity))
            else:
                cleanup_failed = True
        expected_absent = {(type(manager).__name__, identity) for manager, identity in resources}
        expected_absent |= {(type(engine.containers).__name__, identity) for identity in helper_ids}
        engine.close()
        if cleanup_failed or absent != expected_absent:
            raise RuntimeError("numeric bootstrap fixture cleanup incomplete")
    print(json.dumps({"status": "passed", "source_product": True, "both_bootstrap_files": True,
                      "numeric_uid": 10006, "readonly": True, "other_uid_denied": True,
                      "authenticated_provider": True, "redaction": True, "residue": "absent"}))


if __name__ == "__main__":
    main()
