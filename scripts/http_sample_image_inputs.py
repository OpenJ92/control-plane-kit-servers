"""Shared public image-input codec; no fixture, provider or runtime work."""
import json
import os
import sys

from control_plane_kit_core.products import OciImageReference, OciImageReferenceCodec

IMAGE_ROLES = frozenset({"cpk", "postgres", "secrets", "website", "gateway", "connector"})


def require_images(images):
    if type(images) is not dict or images.keys() != IMAGE_ROLES:
        raise ValueError("source assembly requires all six explicit immutable images")
    codec = OciImageReferenceCodec()
    if any(type(value) is not OciImageReference or codec.decode(codec.encode(value)) != value
            for value in images.values()):
        raise ValueError("source assembly requires all six explicit immutable images")
    return dict(images)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate full image input key")
        result[key] = value
    return result


def image_options(environment):
    full = environment.get("CPK_SOURCE_ASSEMBLY_IMAGES")
    legacy = environment.get("CPK_SOURCE_ASSEMBLY_POSTGRES_IMAGE")
    if full is not None:
        if legacy is not None:
            raise ValueError("source assembly image inputs conflict")
        document = json.loads(full, object_pairs_hook=_unique)
        if type(document) is not dict or document.keys() != IMAGE_ROLES:
            raise ValueError("source assembly requires all six explicit immutable images")
        return {"images":require_images({role:OciImageReferenceCodec().decode(value)
            for role, value in document.items()})}
    # Preserve the established legacy JSON parser, including its duplicate policy.
    return {"postgres_image":None if legacy is None else OciImageReferenceCodec().decode(json.loads(legacy))}


if __name__ == "__main__":
    try:
        image_options(os.environ)
    except Exception:
        print("source assembly image input refused", file=sys.stderr)
        raise SystemExit(2) from None
