"""Public installed-source evidence inside the actual Secrets product image."""
from importlib import import_module, metadata
import json
from pathlib import Path
import subprocess
import sys


def provenance(coordinates):
    origins = {}
    for name in ("core", "server-sdk", "secrets"):
        distribution = "control-plane-kit-" + name
        commit = coordinates["upstreams"]["control_plane_kit_" + name.replace("-", "_") + "_commit"]
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
    checked = subprocess.run([sys.executable, "-m", "pip", "check"],
        capture_output=True, timeout=30, check=False)
    if checked.returncode != 0:
        raise ValueError("installed dependency check failed")
    return {"installed_origins": origins, "pip_check": "passed", "server_import": "passed"}


if __name__ == "__main__":
    try:
        result = provenance(json.loads(Path(sys.argv[1]).read_text()))
    except Exception:
        print("Secrets packaged provenance unavailable", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))
