"""Bounded CPK account evidence; maintained umoci owns all filesystem unpacking."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


OCI = "application/vnd.oci.image."
DOCKER = "application/vnd.docker.distribution."
MANIFESTS = {OCI + "manifest.v1+json", DOCKER + "manifest.v2+json"}
INDEXES = {OCI + "index.v1+json", DOCKER + "manifest.list.v2+json"}
CONFIGS = {OCI + "config.v1+json", "application/vnd.docker.container.image.v1+json"}
LAYERS = {OCI + "layer.v1.tar", OCI + "layer.v1.tar+gzip", "application/vnd.docker.image.rootfs.diff.tar.gzip"}
JSON_LIMIT = 1024 * 1024
ACCOUNT_LIMIT = 65536
COMPRESSED_LIMIT = 2 * 1024**3
UMOCI_SHA256 = "b51c267ec394499e42c6fde47f240b7b7dba57ea49df0b5acd304378b82a3b71"


class AccountInspectionError(ValueError):
    def __init__(self):
        super().__init__("root image account inspection refused")


def require(value):
    if not value:
        raise AccountInspectionError()


def digest(value):
    return type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def document(raw):
    require(type(raw) is bytes and 0 < len(raw) <= JSON_LIMIT)
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result
    def constant(unused):
        raise AccountInspectionError()
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    require(type(value) is dict)
    return value


@contextmanager
def directory(parent, name):
    require(type(name) is str and name not in ("", ".", "..") and "/" not in name)
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield fd
    finally:
        os.close(fd)


def read_file(parent, name, limit, *, expected=None, collect=True):
    require(type(name) is str and name not in ("", ".", "..") and "/" not in name)
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(fd, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and 0 <= metadata.st_size <= limit)
        if expected is not None:
            require(metadata.st_size == expected["size"])
        hasher, chunks, size = hashlib.sha256(), [], 0
        while chunk := stream.read(min(65536, limit - size + 1)):
            size += len(chunk)
            require(size <= limit)
            hasher.update(chunk)
            if collect:
                chunks.append(chunk)
        require(size == metadata.st_size)
        if expected is not None:
            require("sha256:" + hasher.hexdigest() == expected["digest"])
        return b"".join(chunks) if collect else hasher.hexdigest()


def descriptor(value, media, limit):
    require(type(value) is dict and value.get("mediaType") in media and digest(value.get("digest")))
    require(type(value.get("size")) is int and 0 < value["size"] <= limit)
    require("urls" not in value and "data" not in value)
    return value


def blob(blobs, value, *, collect=True):
    return read_file(blobs, value["digest"][7:], value["size"], expected=value, collect=collect)


def selected_manifest(original, platform_raw, reference):
    require(type(reference) is str and re.fullmatch(
        r"ghcr\.io/openj92/control-plane-kit-servers/cpk-server@sha256:[0-9a-f]{64}", reference) is not None)
    require(sha(original) == reference.split("@", 1)[1])
    root = document(original)
    require(root.get("schemaVersion") == 2 and type(root["schemaVersion"]) is int)
    if root.get("mediaType") in INDEXES:
        entries = root.get("manifests")
        require(type(entries) is list and 0 < len(entries) <= 128)
        selected = []
        for entry in entries:
            descriptor(entry, MANIFESTS, JSON_LIMIT)
            platform = entry.get("platform")
            require(type(platform) is dict)
            if platform.get("os") == "linux" and platform.get("architecture") == "amd64":
                require(platform.get("variant") in (None, ""))
                selected.append(entry)
        require(len(selected) == 1)
        require(len(platform_raw) == selected[0]["size"] and sha(platform_raw) == selected[0]["digest"])
    else:
        require(root.get("mediaType") in MANIFESTS and platform_raw == original)
    manifest = document(platform_raw)
    require(type(manifest.get("schemaVersion")) is int and manifest["schemaVersion"] == 2
        and manifest.get("mediaType") in MANIFESTS)
    return manifest


def verify_layout(input_fd, reference, source):
    require(type(source) is str and re.fullmatch(r"[0-9a-f]{40}", source) is not None)
    original = read_file(input_fd, "original.json", JSON_LIMIT)
    platform_raw = read_file(input_fd, "platform.json", JSON_LIMIT)
    original_manifest = selected_manifest(original, platform_raw, reference)
    source_config = descriptor(original_manifest.get("config"), CONFIGS, JSON_LIMIT)
    source_layers = original_manifest.get("layers")
    require(type(source_layers) is list and 0 < len(source_layers) <= 128)
    for layer in source_layers:
        descriptor(layer, LAYERS, COMPRESSED_LIMIT)
    is_oci = original_manifest["mediaType"] == OCI + "manifest.v1+json"
    require(source_config["mediaType"] == (OCI + "config.v1+json" if is_oci
        else "application/vnd.docker.container.image.v1+json"))
    require(all(layer["mediaType"] in ({OCI + "layer.v1.tar", OCI + "layer.v1.tar+gzip"} if is_oci
        else {"application/vnd.docker.image.rootfs.diff.tar.gzip"}) for layer in source_layers))
    require(sum(layer["size"] for layer in source_layers) <= COMPRESSED_LIMIT)
    with directory(input_fd, "layout") as layout:
        require(document(read_file(layout, "oci-layout", JSON_LIMIT)) == {"imageLayoutVersion": "1.0.0"})
        index = document(read_file(layout, "index.json", JSON_LIMIT))
        require(type(index.get("schemaVersion")) is int and index["schemaVersion"] == 2)
        entries = index.get("manifests")
        require(type(entries) is list and len(entries) == 1)
        normalized_descriptor = descriptor(entries[0], {OCI + "manifest.v1+json"}, JSON_LIMIT)
        require(normalized_descriptor.get("annotations", {}).get("org.opencontainers.image.ref.name") == "inspected")
        with directory(layout, "blobs") as blobs_root, directory(blobs_root, "sha256") as blobs:
            normalized_raw = blob(blobs, normalized_descriptor)
            normalized = document(normalized_raw)
            require(type(normalized.get("schemaVersion")) is int and normalized["schemaVersion"] == 2
                and normalized.get("mediaType") == OCI + "manifest.v1+json")
            config_descriptor = descriptor(normalized.get("config"), {OCI + "config.v1+json"}, JSON_LIMIT)
            require(all(config_descriptor[key] == source_config[key] for key in ("digest", "size")))
            layers = normalized.get("layers")
            require(type(layers) is list and len(layers) == len(source_layers))
            for actual, expected in zip(layers, source_layers):
                descriptor(actual, {OCI + "layer.v1.tar", OCI + "layer.v1.tar+gzip"}, COMPRESSED_LIMIT)
                expected_media = (OCI + "layer.v1.tar+gzip" if expected["mediaType"] ==
                    "application/vnd.docker.image.rootfs.diff.tar.gzip" else expected["mediaType"])
                require(actual["mediaType"] == expected_media)
                require(all(actual[key] == expected[key] for key in ("digest", "size")))
                blob(blobs, actual, collect=False)
            config = document(blob(blobs, config_descriptor))
            require(config.get("os") == "linux" and config.get("architecture") == "amd64")
            configured = config.get("config")
            require(type(configured) is dict and configured.get("User") == "10001")
            require(type(configured.get("Labels")) is dict
                and configured["Labels"].get("org.opencontainers.image.revision") == source)
            rootfs = config.get("rootfs")
            require(type(rootfs) is dict and rootfs.get("type") == "layers")
            diffs = rootfs.get("diff_ids")
            require(type(diffs) is list and len(diffs) == len(layers) and all(digest(value) for value in diffs))
    return {"image_reference": reference, "source_revision": source,
        "platform_manifest_digest": sha(platform_raw), "normalized_manifest_digest": sha(normalized_raw),
        "config_digest": config_descriptor["digest"], "layer_count": len(layers), "platform": "linux/amd64"}


def number(value):
    require(re.fullmatch(r"0|[1-9][0-9]{0,9}", value) is not None and int(value) < 2**31)
    return int(value)


def project_accounts(bundle_fd):
    with directory(bundle_fd, "rootfs") as root, directory(root, "etc") as etc:
        passwd = read_file(etc, "passwd", ACCOUNT_LIMIT)
        group = read_file(etc, "group", ACCOUNT_LIMIT)
    users, groups = [], []
    for raw, count, target in ((passwd, 7, users), (group, 4, groups)):
        text = raw.decode("ascii")
        require(text.endswith("\n") and "\x00" not in text and "\r" not in text)
        for line in text.splitlines():
            fields = line.split(":")
            require(len(fields) == count and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*\$?", fields[0]) is not None)
            number(fields[2])
            if count == 7:
                number(fields[3])
            target.append(fields)
    chosen = [user for user in users if user[0] == "cpk" or number(user[2]) == 10001]
    require(len(chosen) == 1 and chosen[0][0] == "cpk" and number(chosen[0][2]) == 10001)
    primary = number(chosen[0][3])
    require(len([entry for entry in groups if number(entry[2]) == primary]) == 1)
    names, gids, supplementary = set(), set(), set()
    for entry in groups:
        gid = number(entry[2])
        require(entry[0] not in names and gid not in gids)
        names.add(entry[0])
        gids.add(gid)
        members = entry[3].split(",") if entry[3] else []
        require(all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*\$?", value) is not None for value in members)
            and len(members) == len(set(members)))
        if "cpk" in members and gid != primary:
            supplementary.add(gid)
    return {"passwd_sha256": hashlib.sha256(passwd).hexdigest(), "group_sha256": hashlib.sha256(group).hexdigest(),
        "uid": 10001, "primary_gid": primary, "supplementary_gids": sorted(supplementary)}


def inspect_offline(reference, source):
    """Fixed mounts supplied by the separately released bounded invocation."""
    input_fd = os.open("/input", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    tools_fd = os.open("/tools", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        evidence = verify_layout(input_fd, reference, source)
        require(read_file(tools_fd, "umoci", 32 * 1024**2, collect=False) == UMOCI_SHA256)
        # /inspection must be a bounded, private, noexec tmpfs in the reviewed
        # invocation. No caller-supplied account path or success flag is accepted.
        parent = Path(tempfile.mkdtemp(prefix="cpk-account-", dir="/inspection"))
        bundle = parent / "bundle"
        completed = subprocess.run(["/tools/umoci", "unpack", "--rootless", "--image",
            "/input/layout:inspected", str(bundle)], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=False)
        require(completed.returncode == 0)
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with directory(parent_fd, "bundle") as bundle_fd:
                accounts = project_accounts(bundle_fd)
        finally:
            os.close(parent_fd)
        return {**evidence, **accounts, "umoci_version": "0.6.0", "umoci_sha256": UMOCI_SHA256,
            "unpack": "complete", "layer_diff_ids": "verified-by-umoci"}
    finally:
        os.close(tools_fd)
        os.close(input_fd)


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 3)
        result = inspect_offline(sys.argv[1], sys.argv[2])
        rendered = json.dumps(result, sort_keys=True, separators=(",", ":"))
        require(len(rendered) <= 4096)
    except Exception:
        print("root image account inspection refused", file=sys.stderr)
        raise SystemExit(1) from None
    print(rendered)
