"""Build-only collection of the pinned cloudflared source's notice files."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import time
from urllib.request import urlopen


SOURCE = "81a53555aa827fca88605d7e67ad5c03cda468d2"
NOTICE_NAMES = frozenset(("LICENSE", "NOTICE", "COPYING", "PATENTS"))


def main():
    manifest_bytes = Path(__file__).with_name("cloudflared-manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["source_commit"] != SOURCE:
        raise ValueError("unexpected notice source")
    expected = {}
    for item in manifest["notices"]:
        path = PurePosixPath(item["path"])
        if (path.is_absolute() or ".." in path.parts or str(path) != item["path"]
                or path.name.upper().split(".", 1)[0] not in NOTICE_NAMES
                or item["path"] in expected):
            raise ValueError("invalid notice manifest path")
        expected[item["path"]] = item["sha"]
    if not expected:
        raise ValueError("empty notice manifest")

    deadline = time.monotonic() + 120
    data = bytearray()
    # One exact public source fetch, no fallback revision or retry loop.
    with urlopen("https://codeload.github.com/cloudflare/cloudflared/tar.gz/" + SOURCE,
                 timeout=30) as response:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("notice download deadline")
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            if len(data) + len(chunk) > 64 * 1024 * 1024:
                raise ValueError("notice archive exceeds bound")
            data.extend(chunk)

    prefix = "cloudflared-" + SOURCE + "/"
    destination = Path("/licenses/cloudflared")
    found = set()
    expanded = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r|gz") as archive:
        for index, member in enumerate(archive):
            if time.monotonic() > deadline or index >= 50000:
                raise ValueError("notice archive traversal exceeds bound")
            expanded += member.size
            if member.size < 0 or expanded > 512 * 1024 * 1024:
                raise ValueError("expanded notice archive exceeds bound")
            if member.name.rstrip("/") == prefix.rstrip("/"):
                continue
            if not member.name.startswith(prefix):
                raise ValueError("unexpected source archive prefix")
            relative = PurePosixPath(member.name[len(prefix):])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("invalid source archive path")
            if relative.name.upper().split(".", 1)[0] not in NOTICE_NAMES:
                continue
            key = str(relative)
            if not member.isfile() or key not in expected or key in found:
                raise ValueError("source notice inventory differs from manifest")
            if member.size > 8 * 1024 * 1024:
                raise ValueError("source notice exceeds bound")
            with archive.extractfile(member) as source:
                content = source.read(8 * 1024 * 1024 + 1)
            if len(content) != member.size:
                raise ValueError("incomplete source notice")
            blob = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
            if hashlib.sha1(blob, usedforsecurity=False).hexdigest() != expected[key]:
                raise ValueError("source notice blob differs from manifest")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o444)
            found.add(key)
    if found != set(expected):
        raise ValueError("source notice inventory is incomplete")
    recorded = destination / "source-manifest.json"
    recorded.write_bytes(manifest_bytes)
    recorded.chmod(0o444)
    print("cloudflared source notice inventory and blobs verified:", len(found))


if __name__ == "__main__":
    main()
