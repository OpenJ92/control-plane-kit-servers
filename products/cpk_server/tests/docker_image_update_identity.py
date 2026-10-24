"""Fixed-artifact proof for the owning witnesses and socket-free CI verifier."""
from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from types import MappingProxyType


ROOT = Path(__file__).parent
MANIFEST_MEDIA = "application/vnd.docker.distribution.manifest.v2+json"
CONFIG_MEDIA = "application/vnd.docker.container.image.v1+json"
LAYER_MEDIA = "application/vnd.docker.image.rootfs.diff.tar.gzip"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
EXTRA_REFERENCE = re.compile(
    r"ghcr\.io/openj92/control-plane-kit-servers/(hello-server|cpk-local-gateway)@sha256:[0-9a-f]{64}\Z")
FIXED = MappingProxyType({role: MappingProxyType(value) for role, value in json.loads(
    (ROOT / "docker_image_update_images.json").read_text()).items()})


def require(condition):
    if not condition:
        raise ValueError("fixed artifact identity proof refused")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("artifact metadata is malformed") from error


def _descriptor(value, media):
    require(type(value) is dict and value.get("mediaType") == media)
    require(type(value.get("digest")) is str and DIGEST.fullmatch(value["digest"]) is not None)
    require(type(value.get("size")) is int and 0 < value["size"] <= 2**63 - 1)


def _daemon(value):
    require(type(value) is str and 0 < len(value) <= 256 and value.isascii()
            and value.isprintable() and not value.isspace())


def fixed_manifest_bytes(role):
    require(type(role) is str and role in FIXED)
    path = ROOT / "docker_image_update_manifests" / (FIXED[role]["reference"].split("@sha256:")[1] + ".json")
    with path.open("rb") as stream:
        raw = stream.read(65537)
    require(0 < len(raw) <= 65536)
    return raw


@dataclass(frozen=True, slots=True)
class FixedImageProof:
    role: str
    reference: str
    manifest_digest: str
    config_digest: str
    execution_id: str
    proof_form: str
    platform: str

    def __post_init__(self):
        require(type(self.role) is str and self.role in FIXED)
        expected = FIXED[self.role]
        require(self.reference == expected["reference"]
                and self.manifest_digest == self.reference.split("@")[1]
                and self.config_digest == expected["image_id"]
                and self.manifest_digest != self.config_digest and self.platform == "linux/amd64")
        require((self.proof_form == "config-valued" and self.execution_id == self.config_digest)
                or (self.proof_form == "manifest-valued" and self.execution_id == self.manifest_digest))


@dataclass(frozen=True, slots=True)
class FixedImages:
    daemon_id: str
    images: Mapping

    def __post_init__(self):
        _daemon(self.daemon_id)
        require(isinstance(self.images, Mapping) and set(self.images) == set(FIXED))
        for role, proof in self.images.items():
            require(type(proof) is FixedImageProof and proof.role == role)
            proof.__post_init__()
        object.__setattr__(self, "images", MappingProxyType(dict(self.images)))

    def descriptor(self):
        return {"daemon_id": self.daemon_id,
                "images": {role: asdict(proof) for role, proof in self.images.items()}}


def bind_fixed_images(daemon_id, proofs):
    return FixedImages(daemon_id, proofs)


def qualify_fixed_image(role, *, reference, manifest_bytes, image_attrs, interpreter_image_id=None):
    require(type(role) is str and role in FIXED and reference == FIXED[role]["reference"])
    expected = FIXED[role]
    manifest_digest = reference.split("@")[1]
    require(type(manifest_bytes) is bytes and 0 < len(manifest_bytes) <= 65536)
    require("sha256:" + hashlib.sha256(manifest_bytes).hexdigest() == manifest_digest)
    manifest = _json(manifest_bytes)
    require(type(manifest) is dict and type(manifest.get("schemaVersion")) is int
            and manifest["schemaVersion"] == 2 and manifest.get("mediaType") == MANIFEST_MEDIA
            and "manifests" not in manifest)
    _descriptor(manifest.get("config"), CONFIG_MEDIA)
    require(manifest["config"]["digest"] == expected["image_id"])
    layers = manifest.get("layers")
    require(type(layers) is list and 0 < len(layers) <= 32)
    for layer in layers:
        _descriptor(layer, LAYER_MEDIA)
    attrs = image_attrs
    require(type(attrs) is dict and attrs.get("Os") == "linux" and attrs.get("Architecture") == "amd64")
    digests = attrs.get("RepoDigests")
    require(type(digests) is list and reference in digests)
    config = attrs.get("Config")
    require(type(config) is dict and config.get("User") == expected["user"])
    if "source_revision" in expected:
        labels = config.get("Labels")
        require(type(labels) is dict and labels.get("org.opencontainers.image.revision") == expected["source_revision"])
    if role == "connector":
        require(config.get("Entrypoint") == ["/pause"])
    identity = attrs.get("Id")
    require(type(identity) is str and DIGEST.fullmatch(identity) is not None)
    if interpreter_image_id is not None:
        require(type(interpreter_image_id) is str and interpreter_image_id == identity)
    descriptor = attrs.get("Descriptor")
    if descriptor is not None:
        _descriptor(descriptor, MANIFEST_MEDIA)
        require(descriptor["digest"] == manifest_digest and descriptor["size"] == len(manifest_bytes))
        if "platform" in descriptor:
            platform = descriptor["platform"]
            require(type(platform) is dict and platform.get("os") == "linux"
                    and platform.get("architecture") == "amd64"
                    and set(platform) <= {"os", "architecture", "variant"}
                    and platform.get("variant", "") == "")
    require(manifest_digest != expected["image_id"])
    if identity == expected["image_id"]:
        form = "config-valued"
    elif identity == manifest_digest:
        require(descriptor is not None)
        form = "manifest-valued"
    else:
        raise ValueError("artifact execution identity is unrelated")
    return FixedImageProof(role, reference, manifest_digest, expected["image_id"], identity, form, "linux/amd64")


def qualify_preloaded_images(*, daemon_id, image_attrs_by_reference, optional_references=()):
    """Actual preload caller: fixed references cannot be demoted by optional inputs."""
    _daemon(daemon_id)
    require(type(image_attrs_by_reference) is dict and type(optional_references) in (list, tuple)
            and len(optional_references) <= 3)
    fixed_references = {value["reference"] for value in FIXED.values()}
    require(all(type(ref) is str and EXTRA_REFERENCE.fullmatch(ref) is not None
                for ref in optional_references))
    require(set(image_attrs_by_reference) == fixed_references | set(optional_references))
    proofs = {role: qualify_fixed_image(role, reference=value["reference"],
        manifest_bytes=fixed_manifest_bytes(role), image_attrs=image_attrs_by_reference[value["reference"]])
        for role, value in FIXED.items()}
    additional = []
    for reference in sorted(set(optional_references) - fixed_references):
        attrs = image_attrs_by_reference[reference]
        require(type(attrs) is dict and attrs.get("Os") == "linux" and attrs.get("Architecture") == "amd64")
        require(type(attrs.get("RepoDigests")) is list and reference in attrs["RepoDigests"])
        require(type(attrs.get("Id")) is str and DIGEST.fullmatch(attrs["Id"]) is not None)
        additional.append({"reference": reference, "execution_id": attrs["Id"], "platform": "linux/amd64"})
    return {"fixed": bind_fixed_images(daemon_id, proofs).descriptor(), "additional": additional}


def main():
    require(len(sys.argv) == 2)
    with Path(sys.argv[1]).open("rb") as stream:
        raw = stream.read(262145)
    require(0 < len(raw) <= 262144)
    value = _json(raw)
    require(type(value) is dict and set(value) == {"daemon_id", "image_attrs_by_reference", "optional_references"})
    print(json.dumps(qualify_preloaded_images(**value), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, TypeError):
        raise SystemExit("artifact preload qualification refused") from None
