"""Public installed-source evidence inside the actual Secrets product image."""
from importlib import import_module, metadata
import json
from pathlib import Path
import subprocess
import sys


PARENT_SECRETS = "57e4fc61d6931ef078550f98154a585bda61987b"


def provenance(coordinates, *, parent=False):
    origins = {}
    for name in ("core", "server-sdk", "secrets"):
        distribution = "control-plane-kit-" + name
        commit = coordinates["upstreams"]["control_plane_kit_" + name.replace("-", "_") + "_commit"]
        if parent and name == "secrets":
            commit = PARENT_SECRETS
        repository = "control-plane-kit" if name == "core" else distribution
        expected = "https://github.com/OpenJ92/" + repository + "/archive/" + commit + ".zip"
        direct = json.loads(metadata.distribution(distribution).read_text("direct_url.json"))
        if direct.get("url") != expected or direct.get("subdirectory") != (
                distribution if name == "core" else None):
            raise ValueError("installed source mismatch")
        origins[distribution] = {"url": expected, "subdirectory": direct.get("subdirectory")}
    server = import_module("control_plane_kit_servers_secrets_server.server")
    if not Path(server.__file__).resolve().is_relative_to(Path("/opt/cpk-secrets-product")):
        raise ValueError("product import mismatch")
    if parent:
        from hashlib import sha256
        policy = import_module("control_plane_kit_secrets.provider_policy")
        expected = Path(metadata.distribution("control-plane-kit-secrets").locate_file(
            "control_plane_kit_secrets/provider_policy.py")).resolve()
        if (Path(policy.__file__).resolve() != expected or sha256(expected.read_bytes()).hexdigest() !=
                "532d51ee8f3bece38a379651c16d503a86201380f7e4cb04f1b4ed6a8de86285"):
            raise ValueError("installed parent policy source mismatch")
    checked = subprocess.run([sys.executable, "-m", "pip", "check"],
        capture_output=True, timeout=30, check=False)
    if checked.returncode != 0:
        raise ValueError("installed dependency check failed")
    return {"installed_origins": origins, "pip_check": "passed", "server_import": "passed"}


if __name__ == "__main__":
    try:
        if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--parent"):
            raise ValueError
        result = provenance(json.loads(Path(sys.argv[1]).read_text()), parent=len(sys.argv) == 3)
    except Exception:
        print("Secrets packaged provenance unavailable", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))
