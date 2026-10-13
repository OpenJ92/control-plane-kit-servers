"""CPK recipient proof within the owning numeric bootstrap Docker fixture."""

from __future__ import annotations

import hashlib
from ipaddress import ip_address
from itertools import islice
import json
import secrets
from uuid import uuid4

from control_plane_kit_core.secrets import SecretFileMode, SecretValue
from control_plane_kit_interpreters.docker import DockerSdkSecretMount


def _network_shape(attrs):
    """Bounded flags from the existing adjacent inspect; never emit provider values."""
    def field(parent, key):
        present = type(parent) is dict and key in parent
        value = parent.get(key) if present else None
        kind = next((label for cls, label in (
            (dict, "object"), (str, "string"), (list, "array"),
            (bool, "boolean"), (int, "integer"), (float, "number"),
            (type(None), "null")) if type(value) is cls), "other")
        canonical_ip = False
        if type(value) is str and 1 <= len(value) <= 45 and "%" not in value:
            try:
                canonical_ip = str(ip_address(value)) == value
            except ValueError:
                canonical_ip = False
        return {"present": present, "type": kind,
            "empty": type(value) is str and value == "",
            "canonical_id": type(value) is str and len(value) == 64
                and all(char in "0123456789abcdef" for char in value),
            "canonical_ip": canonical_ip}

    settings = attrs.get("NetworkSettings") if type(attrs) is dict else None
    networks = settings.get("Networks") if type(settings) is dict else None
    state = attrs.get("State") if type(attrs) is dict else None
    running = state.get("Running") if type(state) is dict else None
    entries = tuple(islice(networks.values(), 64)) if type(networks) is dict else ()
    return {"running": running if type(running) is bool else None,
        "settings": field(attrs, "NetworkSettings"), "networks": field(settings, "Networks"),
        "entry_count_capped": min(len(networks), 65) if type(networks) is dict else None,
        "entries": [{"object": type(entry) is dict,
            "network_id": field(entry, "NetworkID"), "address": field(entry, "IPAddress")}
            for entry in entries]}


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
'''
    name = f"cpk-client-recipient-{uuid4().hex}"
    mount = DockerSdkSecretMount(target, volume.name)
    sdk.create_container(name=name, image=image_id, environment={}, labels=labels,
                         volumes={}, secret_mounts=(mount,), network=network_id,
                         aliases=(name,), command=("python", "-B", "-c", probe))
    recipient = engine.containers.get(name)
    resources.append((engine.containers, recipient.id))
    print(json.dumps({"cpk_prestart_network_shape": _network_shape(recipient.attrs)}), flush=True)
    observed = sdk.inspect_container(name)
    assert observed is not None and observed.image_id == image_id
    assert observed.configured_user == "10001"
    assert observed.readonly_secret_mounts == (mount,)
    sdk.start_container(name)
    result = recipient.wait(timeout=30)
    output = recipient.logs(tail=30)
    assert value.encode() not in output, "CPK recipient material leaked"
    assert result.get("StatusCode") == 0, "CPK UID/account/HOME/protected-file law failed"
