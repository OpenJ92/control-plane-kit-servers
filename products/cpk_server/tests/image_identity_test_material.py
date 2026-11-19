"""Finite observations for the fixed #191 artifact proof laws; no effects."""
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parent
FIXED = json.loads((ROOT / "docker_image_update_images.json").read_text())


def manifest_bytes(role):
    digest = FIXED[role]["reference"].split("@sha256:")[1]
    return (ROOT / "docker_image_update_manifests" / (digest + ".json")).read_bytes()


def observations(form="manifest-valued"):
    images = {}
    for role, selected in FIXED.items():
        manifest = selected["reference"].split("@")[1]
        identity = manifest if form == "manifest-valued" else selected["image_id"]
        labels = ({"org.opencontainers.image.revision": selected["source_revision"]}
                  if "source_revision" in selected else {})
        attrs = {"Id": identity, "RepoDigests": [selected["reference"]],
                 "Os": "linux", "Architecture": "amd64",
                 "Config": {"User": selected["user"], "Labels": labels}}
        if role == "connector":
            attrs["Config"]["Entrypoint"] = ["/pause"]
        if form == "manifest-valued":
            attrs["Descriptor"] = {"digest": manifest,
                "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "size": len(manifest_bytes(role))}
        images[role] = attrs
    return images


def clients(form="manifest-valued"):
    images = observations(form)
    by_reference = {FIXED[role]["reference"]: value for role, value in images.items()}
    def image(reference):
        attrs = by_reference[reference]
        return SimpleNamespace(id=attrs["Id"], attrs=attrs, labels=attrs["Config"]["Labels"])
    def inspected(reference):
        attrs = by_reference[reference]
        return SimpleNamespace(image_id=attrs["Id"], repo_digests=tuple(attrs["RepoDigests"]),
                               configured_user=attrs["Config"]["User"])
    engine = SimpleNamespace(info=lambda: {"ID": "daemon-a"},
                             images=SimpleNamespace(get=image))
    sdk = SimpleNamespace(inspect_image=inspected)
    return engine, sdk


def qualified_images(form="config-valued", *, daemon_id="daemon-a"):
    # Future owner is deliberately resolved at call time, never at collection.
    from docker_image_update_identity import bind_fixed_images, qualify_fixed_image
    proofs = {role: qualify_fixed_image(role, reference=FIXED[role]["reference"],
        manifest_bytes=manifest_bytes(role), image_attrs=attrs,
        interpreter_image_id=attrs["Id"]) for role, attrs in observations(form).items()}
    return bind_fixed_images(daemon_id, proofs)
