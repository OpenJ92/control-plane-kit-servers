"""Owned in-container smoke fixture; emits only public JSON and private headers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

# This script is invoked only inside the established test/controller image.
if __name__ == "__main__":
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from cpk_http_host_fixtures import fixture, token
import control_plane_kit_core as core

LIFETIME_SECONDS = 240
MAX_RESPONSE_BYTES = 65_536


def generate(directory: Path) -> None:
    from control_plane_kit_servers_cpk_server.control_configuration import cpk_control_configuration_artifact
    authority=fixture(uuid4().hex,issued_at=int(time.time()),lifetime=LIFETIME_SECONDS)
    artifact=cpk_control_configuration_artifact(authority.config)
    files={
        "control.json":(artifact.content.encode(),0o444),
        "surface.headers":(("Authorization: Bearer "+token(authority,static=True)+"\n").encode(),0o600),
        "health.headers":(("Authorization: Bearer "+token(authority)+"\n").encode(),0o600),
    }
    for name,(content,mode) in files.items():
        descriptor=os.open(directory/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
        with os.fdopen(descriptor,"wb") as stream:
            stream.write(content)
            os.fchmod(stream.fileno(),mode)


def verify(directory: Path) -> None:
    from control_plane_kit_servers_cpk_server.control_configuration import decode_cpk_control_configuration
    control=decode_cpk_control_configuration((directory/"control.json").read_bytes())
    for name in ("surface.json","health.json"):
        with (directory/name).open("rb") as stream:
            raw=stream.read(MAX_RESPONSE_BYTES+1)
        if len(raw)>MAX_RESPONSE_BYTES:
            raise ValueError("smoke control response exceeds bound")
        response=json.loads(raw)
        if name=="surface.json":
            if response.get("declaration") != control.declaration.descriptor():
                raise ValueError("smoke control declaration mismatch")
        else:
            request=core.NodeHealthReadRequest(control.target,control.runtime_id,core.NodeHealthReadKind.LIVENESS,control.declaration.identity(),"health-request")
            result=core.NodeHealthReadResultCodec(request,control.declaration).decode(response)
            if result.outcome is not core.NodeHealthReadOutcome.HEALTHY:
                raise ValueError("smoke liveness is not healthy")


def main() -> int:
    # Fixed errors prevent tracebacks from exposing header or response material.
    accepted=False
    try:
        if len(sys.argv)!=3 or sys.argv[1] not in {"generate","verify"}:
            raise ValueError
        directory=Path(sys.argv[2])
        if sys.argv[1]=="generate":
            generate(directory)
        else:
            verify(directory)
        accepted=True
    except Exception:
        accepted=False
    if not accepted:
        print("CPK synthetic control fixture failed",file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
