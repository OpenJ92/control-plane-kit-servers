"""Verify the selected installed cohort inside the finished product image.

No provider access, secret reads, controller imports or host source mounts.
"""
import base64
import hashlib
import importlib
import importlib.metadata as metadata
import json
import os
import platform
import re
from pathlib import Path
import subprocess
import sys

if not __debug__:
    raise SystemExit("grandparent cohort verification requires enabled checks")

PUBLIC = Path("/usr/share/cpk-grandparent")
BUILD = Path("/opt/cpk-grandparent-build")
PACKAGES = {
    "core": ("control-plane-kit-core", "control_plane_kit_core"),
    "operations": ("control-plane-kit-operations", "control_plane_kit_operations"),
    "interpreters": ("control-plane-kit-interpreters", "control_plane_kit_interpreters"),
    "sdk": ("control-plane-kit-server-sdk", "control_plane_kit_server_sdk"),
}
PRODUCTS = {
    "server": Path("/app/products/cpk_server/src/control_plane_kit_servers_cpk_server"),
    "gateway": Path("/app/products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway"),
}
SOURCE_PREFIXES = {
    "core": "control-plane-kit-core/src/control_plane_kit_core/",
    "operations": "control-plane-kit-operations/src/control_plane_kit_operations/",
    "interpreters": "src/control_plane_kit_interpreters/",
    "sdk": "src/control_plane_kit_server_sdk/",
    "server": "products/cpk_server/src/control_plane_kit_servers_cpk_server/",
    "gateway": "products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/",
}


def files(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()
            and "__pycache__" not in path.parts and path.suffix != ".pyc"}


def seal():
    lock = public_lock(PUBLIC / "public-lock.json")
    expected_requirements = (
        "# Linux amd64 / CPython 3.12 only; no CLI extras.\n"
        "# Version observations: accepted #401 focused default202; hashes: versioned PyPI metadata.\n"
        + "".join(package["name"] + " @ " + package["url"] + " --hash=sha256:" + package["sha256"] + "\n"
                  for package in lock["packages"]))
    assert (PUBLIC / "public-requirements.txt").read_text().rstrip("\n") + "\n" == expected_requirements
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
    raw_origin = dist.read_text("direct_url.json")
    origin = json.loads(raw_origin) if raw_origin else None
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
    assert cohort["schema"] == "cpk399.grandparent-artifact.v1"
    assert cohort["servers"] == "0610e9454dd9a75a6e6bf5e89fe281c8631cccaa"
    assert cohort["source_cohort_schema"] == "cpk163.grandparent-cohort.v2"
    assert cohort["mcp_profile"] == os.environ.get("CPK_MCP_PROFILE") == "grandparent-read-only-v1"
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
    for role in ("interpreters", "sdk"):
        assert any(cohort["declared_core"] in item for item in result["packages"][role]["requires_dist"])
    result["declared_core_url_differs_from_selected_core"] = True
    result["selection"] = "explicit-reviewed-local-artifacts-no-deps-force-reinstall"
    checked = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, check=False)
    assert checked.returncode == 0
    result["pip_check"] = "passed-version-consistency-only"
    result["build_tools"] = {name: metadata.version(name) for name in ("setuptools", "wheel")}
    locked = public_lock(PUBLIC / "public-lock.json")
    for package in locked["packages"]:
        details = distribution(package["name"])
        assert details["version"] == package["version"]
        assert details["direct_url"]["url"] == package["url"]
        assert details["direct_url"]["archive_info"]["hashes"]["sha256"] == package["sha256"]
    mcp_module = importlib.import_module("mcp")
    assert Path(mcp_module.__file__).resolve().parent == Path(
        metadata.distribution("mcp").locate_file("mcp")).resolve()
    assert metadata.version("mcp") == cohort["mcp"] == "2.3.0"
    result["mcp"] = {"version": metadata.version("mcp"), "import_path": str(mcp_module.__file__)}
    result["public_lock_sha256"] = hashlib.sha256((PUBLIC / "public-lock.json").read_bytes()).hexdigest()
    try:
        metadata.distribution("control-plane-kit-secrets")
    except metadata.PackageNotFoundError:
        result["secrets_distribution"] = "not-installed"
    else:
        raise ValueError("unexpected Secrets distribution")
    print(json.dumps(result, sort_keys=True))


def public_lock(path):
    raw = path.read_bytes()
    assert len(raw) <= 65536
    value = json.loads(raw)
    assert value["schema"] == "cpk399.mcp-public-lock.v1"
    assert value["target"] == {"os": "linux", "architecture": "amd64",
        "implementation": "CPython", "python": "3.12"}
    assert len(value["packages"]) == 28
    names = set()
    for package in value["packages"]:
        assert set(package) == {"name", "version", "wheel", "url", "sha256", "metadata_url", "requires_dist"}
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", package["name"])
        assert package["name"] not in names
        names.add(package["name"])
        assert re.fullmatch(r"[0-9a-f]{64}", package["sha256"])
        assert package["url"].startswith("https://files.pythonhosted.org/packages/")
        assert package["url"].endswith("/" + package["wheel"])
        assert package["metadata_url"] == "https://pypi.org/pypi/" + package["name"] + "/" + package["version"] + "/json"
    assert {"mcp", "mcp-types"}.issubset(names)
    return value


def base_public_inventory(path, *, require_match=False):
    """Read public distribution versions only; never import the server or config."""
    lock = public_lock(path)
    assert sys.platform == "linux" and platform.machine() == "x86_64"
    assert sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 12)
    rows, mismatches = {}, []
    for package in lock["packages"]:
        name = package["name"]
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            version = None
        if version is not None:
            assert len(version) <= 128 and re.fullmatch(r"[A-Za-z0-9.+!-]+", version)
        delta = "add" if version is None else "reseal-same-version" if version == package["version"] else "review-required"
        rows[name] = {"observed_version": version, "locked_version": package["version"], "delta": delta}
        if delta == "review-required":
            mismatches.append(name)
    # The retained SDK's actual metadata fixes this shared framework version.
    assert metadata.version("fastapi") == "0.141.1"
    try:
        metadata.distribution("control-plane-kit-secrets")
    except metadata.PackageNotFoundError:
        secrets_absence = "not-installed"
    else:
        raise ValueError("unexpected Secrets distribution")
    result = {"schema": "cpk399.base-public-inventory.v1",
        "status": "review-required" if mismatches else "ready-no-version-changes",
        "public_lock_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "platform": "linux/amd64", "python": "CPython3.12", "packages": rows,
        "mismatches": mismatches, "secrets_distribution": secrets_absence,
        "server_started": False, "credential_or_configuration_read": False}
    print(json.dumps(result, sort_keys=True))
    if require_match and mismatches:
        raise ValueError("base versions require review")


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] in ("base-public", "require-base"):
            base_public_inventory(Path(sys.argv[2]), require_match=sys.argv[1] == "require-base")
        elif sys.argv[1:] == ["seal"]:
            seal()
        elif sys.argv[1:] == ["verify"]:
            verify()
        else:
            raise ValueError
    except Exception:
        print("grandparent installed cohort verification failed", file=sys.stderr)
        raise SystemExit(1) from None
