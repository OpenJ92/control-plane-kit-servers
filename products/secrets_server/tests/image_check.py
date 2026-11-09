"""Public installed-source evidence inside the actual Secrets product image."""
from importlib import import_module, metadata
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys


PARENT_SECRETS = "57e4fc61d6931ef078550f98154a585bda61987b"
PARENT_TREE = "248bc639f5c219fa0b37bcb6e94ced483fae1fc1"
PARENT_PREFIX = "src/control_plane_kit_secrets/"
PARENT_BUILD = Path("/opt/cpk-secrets-parent-build/source")
PARENT_PUBLIC = Path("/usr/share/cpk-secrets-parent")


def source_files(root):
    """Public source content only; same blob-to-file pattern as installer b46d471."""
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("source symlink refused")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def seal_parent(source=PARENT_BUILD, public=PARENT_PUBLIC):
    objects = json.loads((source / ".cpk-source-objects.json").read_text())
    if objects != {"commit":PARENT_SECRETS, "tree":PARENT_TREE, "prefix":PARENT_PREFIX}:
        raise ValueError("parent source objects differ")
    root = source / PARENT_PREFIX
    observed_files = source_files(root)
    blobs = {}
    for line in (source / ".cpk-secrets.git-tree").read_text().splitlines():
        header, path = line.split("\t")
        mode, kind, blob = header.split()
        if mode not in ("100644", "100755") or kind != "blob" or not path.startswith(PARENT_PREFIX):
            raise ValueError("parent source tree differs")
        relative = path.removeprefix(PARENT_PREFIX)
        if ".." in Path(relative).parts or not relative or relative in blobs:
            raise ValueError("parent source tree differs")
        content = (root / relative).read_bytes()
        if hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest() != blob:
            raise ValueError("parent source blob differs")
        blobs[relative] = hashlib.sha256(content).hexdigest()
    if not blobs or observed_files != blobs:
        raise ValueError("parent exported source differs")
    public.mkdir(mode=0o755, parents=True, exist_ok=True)
    with (public / "source-files.json").open("x") as stream:
        json.dump(blobs, stream, sort_keys=True)
    with (public / "source-objects.json").open("x") as stream:
        json.dump(objects, stream, sort_keys=True)
    (public / "source-files.json").chmod(0o444)
    (public / "source-objects.json").chmod(0o444)
    return {"git_commit":PARENT_SECRETS, "source_files_sealed":len(blobs)}


def parent_source_provenance(public=PARENT_PUBLIC):
    objects = json.loads((public / "source-objects.json").read_text())
    if objects != {"commit":PARENT_SECRETS, "tree":PARENT_TREE, "prefix":PARENT_PREFIX}:
        raise ValueError("parent source objects differ")
    dist = metadata.distribution("control-plane-kit-secrets")
    root = Path(dist.locate_file("control_plane_kit_secrets")).resolve()
    module = import_module("control_plane_kit_secrets")
    if Path(module.__file__).resolve().parent != root:
        raise ValueError("parent package import differs")
    expected = json.loads((public / "source-files.json").read_text())
    if not expected or source_files(root) != expected:
        raise ValueError("installed parent source differs")
    records = 0
    for item in dist.files or ():
        if item.hash is None:
            continue
        if item.hash.mode != "sha256":
            raise ValueError("parent distribution record differs")
        digest = base64.urlsafe_b64encode(hashlib.sha256(Path(dist.locate_file(item)).read_bytes()).digest()).decode().rstrip("=")
        if digest != item.hash.value:
            raise ValueError("parent distribution record differs")
        records += 1
    if not records:
        raise ValueError("parent distribution records absent")
    return {"origin":"local-git-export", **objects, "source_files_verified":len(expected),
        "record_files_verified":records, "import_path":str(module.__file__)}


def provenance(coordinates, *, parent=False):
    origins = {}
    for name in ("core", "server-sdk", "secrets"):
        distribution = "control-plane-kit-" + name
        commit = coordinates["upstreams"]["control_plane_kit_" + name.replace("-", "_") + "_commit"]
        if parent and name == "secrets":
            commit = PARENT_SECRETS
        repository = "control-plane-kit" if name == "core" else distribution
        expected = ("file://" + str(PARENT_BUILD) if parent and name == "secrets" else
            "https://github.com/OpenJ92/" + repository + "/archive/" + commit + ".zip")
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
    result = {"installed_origins": origins, "pip_check": "passed", "server_import": "passed"}
    if parent:
        result["parent_source"] = parent_source_provenance()
    return result


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["seal-parent"]:
            result = seal_parent()
        else:
            if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--parent"):
                raise ValueError
            result = provenance(json.loads(Path(sys.argv[1]).read_text()), parent=len(sys.argv) == 3)
    except Exception:
        print("Secrets packaged provenance unavailable", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))
