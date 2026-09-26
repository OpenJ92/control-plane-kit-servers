"""CPK recipient proof within the owning numeric bootstrap Docker fixture."""

from __future__ import annotations

import hashlib
import json
import secrets
from uuid import uuid4

from control_plane_kit_core.secrets import SecretFileMode, SecretValue
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType, ConfigurationFileMode
from control_plane_kit_interpreters.docker import DockerSdkSecretMount, DockerSdkConfigurationMount


def exercise_cpk_file(*, engine, sdk, resources, labels, image_id, network_id):
    """Use the actual image default user; fixture owns exact-resource cleanup."""
    assert engine.images.get(image_id).labels.get("org.openj92.cpk.test-run") == labels[
        "org.openj92.cpk.test-run"
    ]
    image = sdk.inspect_image(image_id)
    assert image is not None and image.image_id == image_id
    uid = image.secret_file_owner_uid()
    assert uid == 10001, "CPK image must advertise numeric UID10001"
    value = secrets.token_urlsafe(48)
    digest = hashlib.sha256(value.encode()).hexdigest()
    target = "/run/secrets/cpk-installation/provider-client"
    volume = engine.volumes.create(name=f"cpk-client-file-{uuid4().hex}", labels=labels)
    resources.append((engine.volumes, volume.name))
    sdk.materialize_secret_file(volume.name, SecretValue(value),
                                SecretFileMode.OWNER_READ_ONLY, owner_uid=uid)
    evidence = sdk.inspect_secret_file(volume.name)
    assert evidence is not None
    assert evidence.uid == uid and evidence.mode == 0o400 and evidence.regular_file
    assert evidence.content_digest == digest, "CPK client material mismatch"
    support = ConfigurationArtifact("managed-health-support", "/etc/cpk/managed-health-support.json",
        ConfigurationMediaType.JSON,
        json.dumps({"profile": "cpk-managed-health-source-support.v1", "products": []}),
        ConfigurationFileMode.READ_ONLY)
    support_volume = engine.volumes.create(name=f"cpk-support-file-{uuid4().hex}", labels=labels)
    resources.append((engine.volumes, support_volume.name))
    sdk.materialize_configuration_artifact(support_volume.name, support)
    assert sdk.configuration_artifact_digest(support_volume.name) == support.content_digest
    support_mount = DockerSdkConfigurationMount(support, support_volume.name)
    probe = f'''
import hashlib, os, pathlib, pwd, stat
account = pwd.getpwnam("cpk")
assert os.getuid() == account.pw_uid == 10001
assert os.getgid() == account.pw_gid
assert os.environ["HOME"] == account.pw_dir
assert os.access(account.pw_dir, os.R_OK | os.X_OK)
file = pathlib.Path({target!r})
info = file.stat()
assert stat.S_ISREG(info.st_mode) and info.st_uid == 10001
assert stat.S_IMODE(info.st_mode) == 0o400
assert hashlib.sha256(file.read_bytes()).hexdigest() == {digest!r}
try:
    file.write_bytes(b"forbidden")
except OSError:
    pass
else:
    raise AssertionError("CPK bootstrap file writable")
import control_plane_kit_servers_cpk_server.server
from control_plane_kit_servers_cpk_server.managed_health_support import read_managed_health_support
support_file = pathlib.Path({support.target_path!r})
support_info = support_file.stat()
assert stat.S_ISREG(support_info.st_mode) and support_info.st_uid == 0
assert stat.S_IMODE(support_info.st_mode) == 0o444
assert hashlib.sha256(support_file.read_bytes()).hexdigest() == {support.content_digest!r}
snapshot = read_managed_health_support(str(support_file))
assert snapshot.products == () and snapshot.receiver_decoders.bindings == ()
try:
    support_file.write_bytes(b"forbidden")
except OSError:
    pass
else:
    raise AssertionError("CPK support file writable")
'''
    name = f"cpk-client-recipient-{uuid4().hex}"
    mount = DockerSdkSecretMount(target, volume.name)
    sdk.create_container(name=name, image=image_id, environment={}, labels=labels,
                         volumes={}, secret_mounts=(mount,), configuration_mounts=(support_mount,), network=network_id,
                         aliases=(name,), command=("python", "-B", "-c", probe))
    recipient = engine.containers.get(name)
    resources.append((engine.containers, recipient.id))
    observed = sdk.inspect_container(name)
    assert observed is not None and observed.image_id == image_id
    assert observed.configured_user == "10001"
    assert {(item.target_path, item.volume_name) for item in observed.readonly_secret_mounts} == {
        (mount.target_path, mount.volume_name), (support.target_path, support_volume.name)}
    sdk.start_container(name)
    result = recipient.wait(timeout=30)
    output = recipient.logs(tail=30)
    assert value.encode() not in output, "CPK recipient material leaked"
    assert result.get("StatusCode") == 0, "CPK UID/account/HOME/protected-file law failed"
    print("CPK UID10001 root-owned0444 support read and packaged codec imports passed")
