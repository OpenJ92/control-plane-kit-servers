"""Verify the selected installed cohort inside the finished product image.

No provider access, secret reads, controller imports or host source mounts.
"""
import base64
import hashlib
import importlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess
import sys

PUBLIC = Path("/usr/share/cpk-grandparent")
BUILD = Path("/opt/cpk-grandparent-build")
PACKAGES = {
    "core": ("control-plane-kit-core", "control_plane_kit_core"),
    "operations": ("control-plane-kit-operations", "control_plane_kit_operations"),
    "interpreters": ("control-plane-kit-interpreters", "control_plane_kit_interpreters"),
}
PRODUCTS = {
    "server": Path("/app/products/cpk_server/src/control_plane_kit_servers_cpk_server"),
    "gateway": Path("/app/products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway"),
}
SOURCE_PREFIXES = {
    "core": "control-plane-kit-core/src/control_plane_kit_core/",
    "operations": "control-plane-kit-operations/src/control_plane_kit_operations/",
    "interpreters": "src/control_plane_kit_interpreters/",
    "server": "products/cpk_server/src/control_plane_kit_servers_cpk_server/",
    "gateway": "products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/",
}


def files(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()
            and "__pycache__" not in path.parts and path.suffix != ".pyc"}


def seal():
    roots = {role: BUILD / role / "src" / package for role, (_, package) in PACKAGES.items()}
    roots.update(PRODUCTS)
    expected = {}
    for role, root in roots.items():
        blobs = {}
        for line in (BUILD / (role + ".git-tree")).read_text().splitlines():
            header, path = line.split("\t")
            mode, kind, blob = header.split()
            assert mode in ("100644", "100755") and kind == "blob" and path.startswith(SOURCE_PREFIXES[role])
            relative = path.removeprefix(SOURCE_PREFIXES[role])
            content = (root / relative).read_bytes()
            assert hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest() == blob
            blobs[relative] = hashlib.sha256(content).hexdigest()
        assert files(root) == blobs
        expected[role] = blobs
    assert all(expected.values())
    (PUBLIC / "source-files.json").write_text(json.dumps(expected, sort_keys=True) + "\n")
    (PUBLIC / "source-objects.json").write_bytes((BUILD / "source-objects.json").read_bytes())


def distribution(name):
    dist = metadata.distribution(name)
    origin = json.loads(dist.read_text("direct_url.json"))
    checked = 0
    for item in dist.files or ():
        if item.hash is None:
            continue
        assert item.hash.mode == "sha256"
        path = Path(dist.locate_file(item))
        observed = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).decode().rstrip("=")
        assert observed == item.hash.value
        checked += 1
    assert checked > 0
    return {"version": dist.version, "direct_url": origin,
            "requires_dist": list(dist.requires or ()), "record_files_verified": checked}


def verify():
    cohort = json.loads((PUBLIC / "cohort.json").read_text())
    expected = json.loads((PUBLIC / "source-files.json").read_text())
    objects = json.loads((PUBLIC / "source-objects.json").read_text())
    for role in (*PACKAGES, *PRODUCTS):
        assert objects[role]["commit"] == cohort["servers" if role in PRODUCTS else role]
        assert objects[role]["prefix"] + "/" == SOURCE_PREFIXES[role]
    result = {"cohort": cohort, "packages": {}, "products": {}, "effective_uid": os.geteuid()}
    result["source_objects"] = objects
    for role, (name, package) in PACKAGES.items():
        module = importlib.import_module(package)
        root = Path(module.__file__).resolve().parent
        assert root == Path(metadata.distribution(name).locate_file(package)).resolve()
        assert files(root) == expected[role]
        details = distribution(name)
        assert details["direct_url"]["url"] == "file:///opt/cpk-grandparent-build/" + role
        details.update(import_path=str(module.__file__), source_files_verified=len(expected[role]))
        if role == "operations":
            sql = sorted(path for path in expected[role] if path.endswith(".sql"))
            assert len(sql) == 7
            details["sql_resources_verified"] = sql
        result["packages"][role] = details
    for role, root in PRODUCTS.items():
        assert files(root) == expected[role]
        module = importlib.import_module("control_plane_kit_servers_cpk_server.server" if role == "server"
                                        else "control_plane_kit_servers_cpk_local_gateway.server")
        assert Path(module.__file__).resolve().is_relative_to(root)
        result["products"][role] = {"import_path": str(module.__file__), "source_files_verified": len(expected[role])}
    sdk = distribution("control-plane-kit-server-sdk")
    assert sdk["direct_url"]["url"] == "https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/" + cohort["sdk"] + ".zip"
    sdk_module = importlib.import_module("control_plane_kit_server_sdk")
    assert Path(sdk_module.__file__).resolve().parent == Path(
        metadata.distribution("control-plane-kit-server-sdk").locate_file("control_plane_kit_server_sdk")).resolve()
    sdk["import_path"] = str(sdk_module.__file__)
    result["packages"]["sdk"] = sdk
    for role in ("interpreters", "sdk"):
        assert any(cohort["declared_core"] in item for item in result["packages"][role]["requires_dist"])
    result["declared_core_url_differs_from_selected_core"] = True
    result["selection"] = "explicit-reviewed-local-artifacts-no-deps-force-reinstall"
    checked = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, check=False)
    assert checked.returncode == 0
    result["pip_check"] = "passed-version-consistency-only"
    result["build_tools"] = {name: metadata.version(name) for name in ("setuptools", "wheel")}
    try:
        result["secrets_distribution"] = distribution("control-plane-kit-secrets")
    except metadata.PackageNotFoundError:
        result["secrets_distribution"] = "not-installed"
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["seal"]:
            seal()
        elif sys.argv[1:] == ["verify"]:
            verify()
        else:
            raise ValueError
    except Exception:
        print("grandparent installed cohort verification failed", file=sys.stderr)
        raise SystemExit(1) from None
