"""Bounded reads against the owned CPK listener, never host-port fallback."""
import json
from pathlib import Path
import signal
import sys
import time

import httpx

from source_control_fixture import verify_response


MAX_RESPONSE_BYTES = 65_536


def request_json(client, path, *, headers=None):
    with client.stream("GET", path, headers=headers) as response:
        raw = bytearray()
        for chunk in response.iter_bytes(chunk_size=4096):
            if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                raise ValueError("owned listener response exceeds bound")
            raw.extend(chunk)
        return response.status_code, json.loads(raw)


def header(directory, name):
    with (directory / name).open("rb") as stream:
        raw = stream.read(16_385)
    if len(raw) > 16_384:
        raise ValueError("owned header exceeds bound")
    value = raw.decode("ascii").removesuffix("\n")
    if not value.startswith("Authorization: Bearer ") or "\n" in value or "\r" in value:
        raise ValueError("owned header is invalid")
    return {"Authorization": value.removeprefix("Authorization: ")}


def check_shared_store(client):
    unsigned, _ = request_json(client, "/workspaces/root-workspace")
    if unsigned != 401:
        raise ValueError("owned workspace authority refusal failed")
    status, body = request_json(client, "/workspaces/root-workspace",
        headers={"Authorization": "Bearer valid-token"})
    if status != 404 or body.get("error", {}).get("status") != 404 or (
            body.get("error", {}).get("message") != "missing workspace 'root-workspace'"):
        raise ValueError("owned shared-store read failed")
    return {"unauthorized_workspace_status": unsigned, "authenticated_workspace_status": status,
        "shared_store_read_verified": True}


def probe(directory, result):
    from control_plane_kit_servers_cpk_server.control_configuration import decode_cpk_control_configuration
    control = decode_cpk_control_configuration((directory / "control.json").read_bytes())
    with httpx.Client(base_url="http://cpk-source:8080", timeout=3, trust_env=False,
            follow_redirects=False) as client:
        result["stage"] = "owned-network-liveness"
        deadline = time.monotonic() + 15
        while True:
            try:
                status, body = request_json(client, "/health/live")
                if status != 200 or body != {"status": "live"}:
                    raise ValueError("owned liveness response is invalid")
                break
            except httpx.HTTPError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        result["live_status"] = status
        result["stage"] = "owned-network-readiness"
        status, body = request_json(client, "/health/ready")
        if status != 200 or body.get("status") != "ready" or body.get("stores") != "configured":
            raise ValueError("owned readiness response is invalid")
        result["ready_status"] = status
        result["stage"] = "owned-source-control"
        surface = header(directory, "surface.headers")
        health = header(directory, "health.headers")
        for path, name, authority in (("capabilities", "surface.json", surface),
                ("health/liveness", "health.json", health)):
            status, body = request_json(client, "/__control/" + path, headers=authority)
            if status != 200:
                raise ValueError("owned control read failed")
            verify_response(control, name, body)
            denied, _ = request_json(client, "/__control/" + path)
            if denied != 401:
                raise ValueError("owned control refusal failed")
        wrong, _ = request_json(client, "/__control/health/liveness", headers=surface)
        if wrong != 401:
            raise ValueError("owned health purpose refusal failed")
        result["source_control_verified"] = True
        result["stage"] = "owned-shared-store-read"
        result.update(check_shared_store(client))
        result["stage"] = "complete"


def main():
    def timed_out(signum, frame):
        raise TimeoutError
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(65)
    result = {"transport": "owned-network", "stage": "read-owned-configuration",
        "live_status": None, "ready_status": None, "source_control_verified": False,
        "shared_store_read_verified": False}
    status = 0
    try:
        if len(sys.argv) != 2:
            raise ValueError("invalid probe arguments")
        probe(Path(sys.argv[1]), result)
    except Exception:
        status = 1
    result["exit_code"] = status
    print(json.dumps(result, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
