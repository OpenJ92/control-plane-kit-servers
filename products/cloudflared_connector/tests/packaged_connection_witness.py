"""Normal test.sh witness inside the source-built product, with no network."""

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from test_connection_readiness import native_body, native_server, response


MODULE = "control_plane_kit_servers_cloudflared_connector.readiness"


def verify_image():
    config = json.loads(Path("/witness-config.json").read_text())
    assert config["User"] == "65532:65532"
    assert (os.getuid(), os.getgid()) == (65532, 65532)
    assert config["Entrypoint"] == [
        "cloudflared", "--no-autoupdate", "--metrics", "127.0.0.1:20241",
    ]
    assert config["Cmd"] == ["tunnel", "run"]
    assert config.get("StopSignal") == "SIGTERM"
    assert not config.get("ExposedPorts")
    check = config["Healthcheck"]
    assert check["Test"] == ["CMD", "python", "-m", MODULE]
    assert check["Interval"] == 5_000_000_000
    assert check["Timeout"] == 3_000_000_000
    assert check["Retries"] == 1
    version = subprocess.run(["cloudflared", "version"], capture_output=True, timeout=5)
    assert version.returncode == 0
    assert b"2026.6.1" in version.stdout
    invalid = subprocess.run(["cloudflared", "cpk-invalid-command"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    assert invalid.returncode != 0


def verify_reader():
    with tempfile.TemporaryDirectory() as directory:
        token = Path(directory) / "token"
        token.write_bytes(b"SYNTHETIC_TOKEN_NOT_A_CREDENTIAL")
        token.chmod(0o400)
        assert token.stat().st_uid == 65532
        assert stat.S_IMODE(token.stat().st_mode) == 0o400
        assert token.read_bytes() == b"SYNTHETIC_TOKEN_NOT_A_CREDENTIAL"
        token.chmod(0)
        denied = False
        try:
            token.read_bytes()
        except PermissionError:
            denied = True
        assert denied, "numeric product UID must not bypass file permissions"
        environment = dict(os.environ, TUNNEL_TOKEN_FILE=str(token))
        for status, count, expected, exit_code in (
            (200, 1, "connected", 0), (503, 0, "disconnected", 1),
        ):
            with native_server(response(native_body(status, count), status)):
                result = subprocess.run([sys.executable, "-m", MODULE], env=environment,
                                        capture_output=True, timeout=4)
            assert result.returncode == exit_code
            assert result.stderr == b""
            assert len(result.stdout) <= 256
            assert json.loads(result.stdout)["outcome"] == expected
            assert b"SYNTHETIC_TOKEN" not in result.stdout
        refused = subprocess.run([sys.executable, "-m", MODULE], env=environment,
                                 capture_output=True, timeout=4)
        assert refused.returncode == 1
        assert refused.stderr == b""
        assert json.loads(refused.stdout)["outcome"] == "unknown"
        forbidden = subprocess.run([sys.executable, "-m", MODULE, "http://example.invalid"],
                                  capture_output=True, timeout=4)
        assert forbidden.returncode == 1
        assert forbidden.stderr == b""
        assert json.loads(forbidden.stdout)["reason"] == "invalid_invocation"


if __name__ == "__main__":
    verify_image()
    verify_reader()
    print("packaged cloudflared evidence and numeric permission witness passed")
