"""Owned smoke file/read fixture; private signing keys never leave generation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import time

MAX_LOG_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 65_536
MAX_HEADER_BYTES = 16_384


def read_file(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError
        raw = stream.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError
    return raw


def generate(directory: Path, run_id: str) -> None:
    from secrets_control_fixtures import SourceControlAuthority
    from control_plane_kit_servers_secrets_server.configuration import secrets_control_configuration_artifact

    authority = SourceControlAuthority(run_id)
    artifact = secrets_control_configuration_artifact(authority.configuration())
    issued_at = int(time.time()) - 1
    files = [("control.json", artifact.content.encode("utf-8"), 0o444)]
    for static, name in ((True, "surface.headers"), (False, "health.headers")):
        _, token = authority.signed_read(static=static, issued_at=issued_at)
        files.append((name, ("Authorization: Bearer " + token + "\n").encode("ascii"), 0o600))
    for name, content, mode in files:
        descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            os.fchmod(stream.fileno(), mode)


def header_token(path: Path) -> str:
    raw = read_file(path, MAX_HEADER_BYTES)
    prefix = b"Authorization: Bearer "
    if not raw.startswith(prefix) or not raw.endswith(b"\n") or raw.count(b"\n") != 1 or b"\r" in raw:
        raise ValueError
    token = raw[len(prefix):-1].decode("ascii")
    if not token or any(character.isspace() for character in token):
        raise ValueError
    return token


def check(directory: Path) -> None:
    import httpx
    import control_plane_kit_core as core
    from control_plane_kit_secrets.control import decode_secrets_control_configuration

    configuration = decode_secrets_control_configuration(read_file(directory / "control.json", MAX_RESPONSE_BYTES))

    def read(path: str, token: str | None = None) -> tuple[int, bytes]:
        headers = {} if token is None else {"Authorization": "Bearer " + token}
        with httpx.stream("GET", "http://secrets-provider:8081" + path,
                          headers=headers, timeout=5, trust_env=False) as response:
            body = bytearray()
            for chunk in response.iter_bytes(chunk_size=4096):
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise ValueError
                body.extend(chunk)
            return response.status_code, bytes(body)

    surface_token = header_token(directory / "surface.headers")
    health_token = header_token(directory / "health.headers")
    surface_request = core.NodeControlSurfaceReadRequest(
        configuration.target, core.NodeControlSurfaceReadKind.CAPABILITIES,
        configuration.declaration.identity(), "source-static",
    )
    status, body = read("/__control/capabilities", surface_token)
    expected = core.NodeControlSurfaceReadResultCodec(surface_request, configuration.declaration).capabilities_result()
    if status != 200 or body != expected.canonical_bytes():
        raise ValueError
    health_request = core.NodeHealthReadRequest(
        configuration.target, configuration.runtime_id, core.NodeHealthReadKind.LIVENESS,
        configuration.declaration.identity(), "source-health",
    )
    status, body = read("/__control/health/liveness", health_token)
    if status != 200:
        raise ValueError
    result = core.NodeHealthReadResultCodec(health_request, configuration.declaration).decode(json.loads(body))
    if result.outcome is not core.NodeHealthReadOutcome.HEALTHY:
        raise ValueError
    for path in ("/__control/capabilities", "/__control/health/liveness"):
        if read(path)[0] != 401:
            raise ValueError
    if read("/__control/health/liveness", surface_token)[0] != 401:
        raise ValueError


def verify_logs(directory: Path, client: Path, phase: Path | None = None) -> None:
    if read_file(directory / "log.status", 32) != b"0\n":
        raise ValueError
    # Empty logs are valid; all other file and overflow laws are the same.
    path = directory / "provider.log"
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError
        body = stream.read(MAX_LOG_BYTES + 1)
    if len(body) > MAX_LOG_BYTES:
        raise ValueError
    forbidden = [b"Bearer ", b"PRIVATE KEY", b"provider-token"]
    forbidden.extend(read_file(client / name, 4096) for name in ("provider-token", "application-value"))
    if phase is not None:
        forbidden.extend(header_token(phase / name).encode("ascii")
                         for name in ("surface.headers", "health.headers"))
    if any(value in body for value in forbidden):
        raise ValueError


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if len(arguments) == 3 and arguments[0] == "generate":
            generate(Path(arguments[1]), arguments[2])
        elif len(arguments) == 2 and arguments[0] == "check":
            check(Path(arguments[1]))
        elif len(arguments) in (3, 4) and arguments[0] == "logs":
            verify_logs(Path(arguments[1]), Path(arguments[2]),
                        Path(arguments[3]) if len(arguments) == 4 else None)
        else:
            raise ValueError
    except Exception:
        print("Secrets smoke fixture failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
