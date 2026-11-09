"""Exclusive synthetic seed for verified fresh owned Secrets custody volumes."""
import json
import os
from pathlib import Path
import secrets
import sys

from control_plane_kit_secrets.crypto import encode_master_key_for_file


def populate(provider, client, data, *, parent=False):
    directories = []
    try:
        for path in (provider, client, data):
            descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            directories.append(descriptor)
            if os.listdir(descriptor):
                raise ValueError("custody volume is not empty")
        token = secrets.token_urlsafe(48)
        grants = [
            {"action":"secret.write","workspace_id":"workspace-image-smoke","intents":["postgres.password"]},
            {"action":"secret.generate-delegation-key","workspace_id":"workspace-image-smoke","intents":["gateway.probe-signing-key"]},
            {"action":"secret.resolve","workspace_id":"workspace-image-smoke","intents":["gateway.probe-signing-key","postgres.password"]},
            {"action":"secret.revoke","workspace_id":"workspace-image-smoke","intents":[]},
        ]
        credentials = [{"subject":"image-smoke-client", "token":token, "grants":grants}]
        parent_payloads = []
        if parent:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from parent_http_roles_fixture import ROLES, WORKSPACE
            for role, intent, _ in ROLES:
                role_token = secrets.token_urlsafe(48)
                credentials.append({"subject":role, "token":role_token, "grants":[
                    {"action":action, "workspace_id":WORKSPACE, "intents":[intent]}
                    for action in ("secret.write", "secret.resolve")]})
                key = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode("ascii")
                parent_payloads.extend(((directories[1],role+".token",role_token,0),
                    (directories[1],role+".key",key,0)))
        payloads = (
            (directories[0],"master.key",encode_master_key_for_file(os.urandom(32)),10006),
            (directories[0],"credentials.json",json.dumps(credentials,separators=(",",":"),sort_keys=True),10006),
            (directories[1],"provider-token",token,0),
            (directories[1],"application-value",secrets.token_urlsafe(40),0),
        ) + tuple(parent_payloads)
        for parent, name, value, owner in payloads:
            descriptor = os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400,dir_fd=parent)
            with os.fdopen(descriptor,"wb") as stream:
                stream.write(value.encode("utf-8"))
                os.fchmod(stream.fileno(),0o400)
                os.fchown(stream.fileno(),owner,owner)
        if set(os.listdir(directories[0])) != {"master.key","credentials.json"} or (
                set(os.listdir(directories[1])) != {item[1] for item in payloads if item[0] == directories[1]}) or os.listdir(directories[2]):
            raise ValueError("custody volume contents changed")
        for index, owner in ((0,10006),(1,0),(2,10006)):
            os.fchmod(directories[index],0o700)
            os.fchown(directories[index],owner,owner)
    finally:
        for descriptor in directories:
            os.close(descriptor)


if __name__ == "__main__":
    try:
        if sys.argv[1:] not in ([], ["--parent"]):
            raise ValueError
        populate(Path("/provider-bootstrap"),Path("/client-bootstrap"),Path("/provider-data"), parent=sys.argv[1:] == ["--parent"])
    except Exception:
        print("Secrets child bootstrap refused",file=sys.stderr)
        raise SystemExit(1) from None
