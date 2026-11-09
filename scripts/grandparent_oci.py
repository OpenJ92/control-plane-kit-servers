"""Validate a bounded local Docker OCI export before BuildKit consumes it."""
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

if not __debug__:
    raise SystemExit("grandparent local OCI validation requires enabled checks")

BASE = "sha256:4846a9005108e925149b2869214c3f32dbdbd4d4953159af532297081e80fe28"
LIMIT = 256 * 1024 * 1024
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def validate_export(archive_path, output, expected=BASE):
    archive_path, output = Path(archive_path), Path(output)
    assert archive_path.stat().st_size <= LIMIT and not any(output.iterdir())
    assert DIGEST.fullmatch(expected)
    sizes = {}
    with tarfile.open(archive_path) as archive:
        members = archive.getmembers()
        assert len(members) <= 4096 and sum(item.size for item in members) <= LIMIT
        names = set()
        for item in members:
            name = item.name.rstrip("/") if item.isdir() else item.name
            assert name not in names
            names.add(name)
            assert name in {"blobs", "blobs/sha256", "oci-layout", "index.json", "manifest.json", "repositories"} or re.fullmatch(r"blobs/sha256/[0-9a-f]{64}", name)
            assert item.isdir() or item.isfile()
            if item.isdir():
                assert name in {"blobs", "blobs/sha256"}
                continue
            if item.name.startswith("blobs/sha256/"):
                path = output / item.name
                path.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.extractfile(item) as source, path.open("xb") as target:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        target.write(chunk)
                assert digest.hexdigest() == path.name
                sizes["sha256:" + path.name] = item.size
            elif item.name in {"oci-layout", "index.json"}:
                assert item.size <= 1024 * 1024
                with archive.extractfile(item) as source:
                    (output / item.name).write_bytes(source.read())
    assert json.loads((output / "oci-layout").read_bytes()) == {"imageLayoutVersion": "1.0.0"}

    def raw(digest):
        assert DIGEST.fullmatch(digest) and digest in sizes and sizes[digest] <= 1024 * 1024
        return json.loads((output / "blobs/sha256" / digest.removeprefix("sha256:")).read_bytes())

    def descriptor(value):
        assert type(value) is dict and DIGEST.fullmatch(value["digest"])
        assert type(value["size"]) is int and sizes[value["digest"]] == value["size"]
        return value["digest"]

    index = json.loads((output / "index.json").read_bytes())
    assert index["schemaVersion"] == 2 and any(descriptor(item) == expected for item in index["manifests"])
    visited = set()

    def visit(digest, depth=0):
        assert depth <= 4
        if digest in visited:
            return
        visited.add(digest)
        value = raw(digest)
        assert value["schemaVersion"] == 2
        if "manifests" in value:
            for item in value["manifests"]:
                visit(descriptor(item), depth + 1)
        else:
            descriptor(value["config"])
            for item in value["layers"]:
                descriptor(item)

    visit(expected)
    base = raw(expected)
    selected = [item for item in base["manifests"] if item.get("platform") == {"architecture": "amd64", "os": "linux"}]
    assert len(selected) == 1
    manifest_digest = descriptor(selected[0])
    manifest = raw(manifest_digest)
    config_digest = descriptor(manifest["config"])
    config = raw(config_digest)
    assert config["os"] == "linux" and config["architecture"] == "amd64"
    assert config["config"]["User"] == "10001" and not config["config"].get("Entrypoint")
    assert config["config"]["Cmd"] == ["python", "-m", "control_plane_kit_servers_cpk_server.server"]
    diff_ids = config["rootfs"]["diff_ids"]
    assert config["rootfs"]["type"] == "layers" and len(diff_ids) == len(manifest["layers"])
    assert all(DIGEST.fullmatch(item) for item in diff_ids)
    return {"base_digest": expected, "manifest_digest": manifest_digest, "config_digest": config_digest,
            "os": "linux", "architecture": "amd64", "blob_count": len(sizes),
            "export_bytes": archive_path.stat().st_size, "blob_bytes": sum(sizes.values()),
            "all_blob_digests_verified": True, "rootfs_diff_ids": diff_ids,
            "base_user": "10001", "base_cmd": config["config"]["Cmd"]}


if __name__ == "__main__":
    try:
        assert len(sys.argv) == 3
        result = validate_export(sys.argv[1], sys.argv[2])
        print(json.dumps(result, sort_keys=True))
    except Exception:
        print("grandparent local OCI base validation failed", file=sys.stderr)
        raise SystemExit(1) from None
