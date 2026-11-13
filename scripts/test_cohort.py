"""Admission and imported-source evidence for the owning grandparent test mode."""
from __future__ import annotations

import base64
import hashlib
import importlib
import importlib.metadata as metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path("/opt/cpk-test-cohort")
MANIFEST = ROOT / "products/cpk_server/grandparent-cohort.json"
EXPECTED = dict(schema="cpk163.grandparent-cohort.v2", name="grandparent", servers="current-head",
    core="f56bb5c4cfde76764d39c5377d4270c5b23c3ba1",
    operations="70154b6698e101159326b08646f2dba90dda87cd",
    interpreters="e438f6e522ad0a23a7acef460be08690f48b2e17",
    sdk="d61b374cb2a23d773c31748f47f88169499298b7", mcp="2.3.0",
    mcp_profile="grandparent-read-only-v1", secrets_distribution="absent")
PACKAGES = {
    "core": ("control-plane-kit-core", "control_plane_kit_core", "control-plane-kit-core/src/"),
    "operations": ("control-plane-kit-operations", "control_plane_kit_operations", "control-plane-kit-operations/src/"),
    "interpreters": ("control-plane-kit-interpreters", "control_plane_kit_interpreters", "src/"),
    "sdk": ("control-plane-kit-server-sdk", "control_plane_kit_server_sdk", "src/"),
}
PRODUCTS = {
    "server": ("control_plane_kit_servers_cpk_server", "products/cpk_server/src/"),
    "gateway": ("control_plane_kit_servers_cpk_local_gateway", "products/cpk_local_gateway/src/"),
}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate cohort field")
        result[key] = value
    return result


def admit(path=MANIFEST):
    raw = path.read_bytes()
    if len(raw) > 16384:
        raise ValueError("cohort manifest too large")
    value = json.loads(raw, object_pairs_hook=unique)
    if value != EXPECTED:
        raise ValueError("cohort manifest differs from approved selection")
    return value


def files(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
        and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def seal():
    admit()
    result = {}
    for role, (_, module, prefix) in PACKAGES.items():
        result[role] = source_files(role, BUILD / role / "src" / module, prefix + module + "/")
    for role, (module, prefix) in PRODUCTS.items():
        result[role] = source_files(role, ROOT / prefix / module, prefix + module + "/")
    (BUILD / "source-files.json").write_text(json.dumps(result, sort_keys=True))


def source_files(role, root, prefix):
    expected = {}
    for line in (BUILD / (role + ".git-tree")).read_text().splitlines():
        header, path = line.split("\t")
        mode, kind, blob = header.split()
        assert mode in ("100644", "100755") and kind == "blob" and path.startswith(prefix)
        relative = path.removeprefix(prefix)
        content = (root / relative).read_bytes()
        assert hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest() == blob
        expected[relative] = hashlib.sha256(content).hexdigest()
    assert expected and files(root) == expected
    return expected


def distribution(name):
    dist = metadata.distribution(name)
    for item in dist.files or ():
        if item.hash is not None:
            assert item.hash.mode == "sha256"
            digest = base64.urlsafe_b64encode(hashlib.sha256(Path(dist.locate_file(item)).read_bytes()).digest())
            assert digest.decode().rstrip("=") == item.hash.value
    return dist


def verify():
    cohort = admit()
    expected = json.loads((BUILD / "source-files.json").read_text())
    evidence = {"cohort": cohort, "candidate_source": (BUILD / "candidate.txt").read_text().strip(),
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(), "packages": {}, "products": {}}
    for role, (name, module_name, _) in PACKAGES.items():
        dist = distribution(name)
        module = importlib.import_module(module_name)
        root = Path(module.__file__).resolve().parent
        assert root == Path(dist.locate_file(module_name)).resolve()
        assert files(root) == expected[role]
        origin = json.loads(dist.read_text("direct_url.json"))
        assert origin["url"] == "file:///opt/cpk-test-cohort/" + role
        evidence["packages"][role] = {"revision": cohort[role], "import_path": str(root),
            "source_files": len(expected[role]), "record_verified": True, "origin": origin}
    for role, (module_name, prefix) in PRODUCTS.items():
        module = importlib.import_module(module_name + ".server")
        root = ROOT / prefix / module_name
        assert Path(module.__file__).resolve().is_relative_to(root)
        assert files(root) == expected[role]
        evidence["products"][role] = {"candidate_source": evidence["candidate_source"],
            "import_path": str(module.__file__), "source_files": len(expected[role])}
    distribution("mcp")
    assert metadata.version("mcp") == cohort["mcp"]
    try:
        metadata.distribution("control-plane-kit-secrets")
    except metadata.PackageNotFoundError:
        pass
    else:
        raise ValueError("unexpected Secrets distribution")
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    if sys.argv[1:] == ["admit"]:
        value = admit()
        print(" ".join(value[role] for role in PACKAGES))
    elif sys.argv[1:] == ["seal"]:
        seal()
    elif sys.argv[1:] == ["verify"]:
        verify()
    else:
        raise SystemExit("unsupported cohort action")
