"""Read only installed provenance inside the CPK image, never an entrypoint shim."""
from importlib import import_module, metadata
import json
from pathlib import Path
import subprocess
import sys


def provenance(coordinates):
    selected = coordinates["upstreams"]
    origins = {}
    for name in ("core", "operations", "interpreters", "server-sdk"):
        distribution = "control-plane-kit-" + name
        repository = "control-plane-kit" if name in ("core", "operations") else distribution
        commit = selected["control_plane_kit_" + name.replace("-", "_") + "_commit"]
        expected = "https://github.com/OpenJ92/" + repository + "/archive/" + commit + ".zip"
        direct = json.loads(metadata.distribution(distribution).read_text("direct_url.json"))
        if direct.get("url") != expected or direct.get("subdirectory") != (
                distribution if name in ("core", "operations") else None):
            raise ValueError("installed source mismatch")
        origins[distribution] = {"url": expected, "subdirectory": direct.get("subdirectory")}
    server = import_module("control_plane_kit_servers_cpk_server.server")
    if not Path(server.__file__).resolve().is_relative_to(Path("/app/products/cpk_server/src")):
        raise ValueError("product import path mismatch")
    checked = subprocess.run([sys.executable, "-m", "pip", "check"],
        capture_output=True, timeout=30, check=False)
    if checked.returncode != 0:
        raise ValueError("installed dependency check failed")
    return {"installed_origins": origins, "pip_check": "passed", "server_import": "passed"}


if __name__ == "__main__":
    try:
        result = provenance(json.loads(Path(sys.argv[1]).read_text()))
    except Exception:
        print("CPK receiver packaged provenance unavailable", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))
