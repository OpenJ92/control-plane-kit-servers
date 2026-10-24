"""Validate read-only GHCR evidence for the one approved Hello destination.

The publisher obtains responses with gh; this module has no network authority.
Run through the existing policy Docker image, never with host Python.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys


REPOSITORY = "ghcr.io/openj92/control-plane-kit-servers/hello-server"
PACKAGE_ID = 13951244


def require(condition: bool) -> None:
    if not condition:
        raise ValueError("Hello publication evidence refused")


def validate(metadata: object, pages: object, source: str, reference: str | None = None) -> dict:
    """Before push require an unused source tag; afterward require its exact digest."""
    require(re.fullmatch(r"[0-9a-f]{40}", source) is not None)
    tag = "hello-271-" + source
    require(isinstance(metadata, dict))
    require(type(metadata.get("id")) is int and metadata["id"] == PACKAGE_ID)
    require(metadata.get("name") == "control-plane-kit-servers/hello-server")
    require(metadata.get("package_type") == "container")
    require(metadata.get("visibility") == "private")
    require(isinstance(metadata.get("repository"), dict))
    require(metadata["repository"].get("full_name") == "OpenJ92/control-plane-kit-servers")
    require(isinstance(pages, list) and bool(pages))
    seen: set[int] = set()
    matches: list[dict] = []
    for page in pages:
        require(isinstance(page, list))
        for version in page:
            require(isinstance(version, dict))
            version_id = version.get("id")
            require(type(version_id) is int and version_id > 0 and version_id not in seen)
            seen.add(version_id)
            require(isinstance(version.get("name"), str))
            require(isinstance(version.get("metadata"), dict))
            container = version["metadata"].get("container")
            require(isinstance(container, dict))
            tags = container.get("tags")
            require(isinstance(tags, list) and all(isinstance(value, str) for value in tags))
            require(len(tags) == len(set(tags)))
            if tag in tags:
                matches.append(version)
    if reference is None:
        require(not matches)
        return {"package_id": PACKAGE_ID, "visibility": "private", "unused_tag": tag}
    require(re.fullmatch(re.escape(REPOSITORY) + r"@sha256:[0-9a-f]{64}", reference) is not None)
    require(len(matches) == 1 and matches[0]["name"] == reference.split("@", 1)[1])
    return {"package_id": PACKAGE_ID, "version_id": matches[0]["id"],
            "visibility": "private", "reference": reference, "tag": tag}


def main() -> int:
    try:
        require(len(sys.argv) in (4, 5))
        directory, source, mode = sys.argv[1:4]
        require(mode in ("before-push", "published"))
        require((mode == "published") == (len(sys.argv) == 5))
        metadata = json.loads((Path(directory) / "package.json").read_text())
        pages = json.loads((Path(directory) / "versions.json").read_text())
        evidence = validate(metadata, pages, source, sys.argv[4] if mode == "published" else None)
        print(json.dumps(evidence, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError):
        print("Hello publication metadata is missing, inconsistent, or not private; stop without retry.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
