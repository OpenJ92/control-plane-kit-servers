"""Shared public image-input codec; no fixture, provider or runtime work."""
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

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


def gateway_document(images):
    """Freeze only declared public slots; no live receiver/trust is needed."""
    from control_plane_kit_core.products import ProductDescriptorCodec
    from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import gateway_http_sample_declared_runtime_contract
    images = require_images(images)
    codec = ProductDescriptorCodec()
    base = codec.decode_document((Path(__file__).resolve().parents[1] /
        "products/cpk_local_gateway/product.cpk.json").read_bytes())
    return codec.encode_document(replace(base.product, image=images["gateway"],
        runtime_contract=gateway_http_sample_declared_runtime_contract()))


def parent_website_input(images, value, *, receiver_id):
    """Public preparation only; caller allocates a fresh parent receiver once."""
    from urllib.parse import urlsplit
    import control_plane_kit_core as core
    from control_plane_kit_servers_website_server import managed
    from control_plane_kit_servers_cpk_server.client.frontend import _canonical_origin
    images = require_images(images)
    expected = {"commissioning_public_document", "commissioning_public_sha256", "installation_id",
        "workspace_id", "api_origin", "website_origin", "host_binding"}
    if type(value) is not dict or value.keys() != expected:
        raise ValueError("parent public website preparation is invalid")
    config = _commissioned_configuration(value, receiver_id)
    target = config.target
    api, site = _canonical_origin(value["api_origin"]), _canonical_origin(value["website_origin"])
    binding = value["host_binding"]
    if (urlsplit(api).hostname.removesuffix(".") == urlsplit(site).hostname.removesuffix(".") or
            type(binding) is not dict or binding.keys() != {"address", "port"} or
            binding["address"] != "127.0.0.1" or type(binding["port"]) is not int or not 1024 <= binding["port"] <= 65535):
        raise ValueError("parent public website preparation is invalid")
    declaration = managed.control_declaration()
    configuration = core.ReceiverNodeControlConfiguration(replace(target,
        node_id=replace(target.node_id, value=value["installation_id"] + "-website"),
        provider_socket_name=declaration.surface.provider_socket_name, receiver_id=receiver_id),
        declaration, config.verifiers)
    artifact = managed.control_configuration_artifact(configuration)
    return {"image":images["website"].descriptor(), "external_endpoint":site,
        "host_binding":binding, "managed_control_configuration":artifact.descriptor()}


def _commissioned_configuration(value, receiver_id):
    from hashlib import sha256
    import control_plane_kit_core as core
    raw = value["commissioning_public_document"]
    if type(raw) is not str or sha256(raw.encode()).hexdigest() != value["commissioning_public_sha256"]:
        raise ValueError("parent public website preparation is invalid")
    public = json.loads(raw, object_pairs_hook=_unique)
    config = core.ReceiverNodeControlConfigurationCodec().decode_bytes(public["artifacts"]["cpk"]["content"].encode())
    target = config.target
    purposes = {core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
        core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ}
    if (public["schema"] != "cpk.root-commissioning.public.v1" or
            {item.purpose for item in config.verifiers} != purposes or len(config.verifiers) != 2 or
            target.workspace_id.value != value["workspace_id"] or
            target.runtime_id.value != value["installation_id"] + "-docker" or
            target.node_id.value != value["installation_id"] + "-cpk" or
            receiver_id in public["receiver_ids"].values()):
        raise ValueError("parent public website preparation is invalid")
    return config


def child_postgres_document(images, value, *, receiver_id):
    """Prepare actual child receiving bytes and the normal installation variant."""
    import control_plane_kit_core as core
    from control_plane_kit_core.products import ProductDescriptorCodec
    from control_plane_kit_core.secrets import SecretReference
    from control_plane_kit_servers_postgres_server import configuration as postgres
    from control_plane_kit_servers_cpk_server.installation import installation_postgres_product
    images = require_images(images)
    if type(value) is not dict or value.keys() != {"commissioning_public_document",
            "commissioning_public_sha256", "installation_id", "workspace_id", "password_reference"}:
        raise ValueError("child public PostgreSQL preparation is invalid")
    config = _commissioned_configuration(value, receiver_id)
    target = config.target
    declaration = postgres.postgres_control_declaration()
    configuration = core.ReceiverNodeControlConfiguration(replace(target,
        node_id=replace(target.node_id, value=value["installation_id"] + "-postgres"),
        provider_socket_name=declaration.surface.provider_socket_name, receiver_id=receiver_id),
        declaration, config.verifiers)
    artifact = postgres.postgres_control_configuration_artifact(configuration)
    codec = ProductDescriptorCodec()
    base = codec.decode_document((Path(__file__).resolve().parents[1] /
        "products/postgres_server/product.cpk.json").read_bytes())
    selected = codec.encode_document(replace(base.product, image=images["postgres"],
        runtime_contract=postgres.postgres_source_runtime_contract(artifact)))
    return codec.encode_document(installation_postgres_product(selected, SecretReference(value["password_reference"])))


def sender_input(gateway_raw, postgres_raw):
    """Existing startup schema; preserve the exact once-prepared PG document."""
    from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference, ProductReferenceCodec
    codec = ProductDescriptorCodec()
    gateway = codec.decode_document(gateway_raw.encode())
    postgres = codec.decode_document(postgres_raw.encode())
    if gateway.content.decode() != gateway_raw or postgres.content.decode() != postgres_raw:
        raise ValueError("sender inputs must be canonical product document bytes")
    return {"schema":"cpk-server.managed-verification.v1",
        "gateway_product":ProductReferenceCodec().encode(ProductReference.from_document(gateway)),
        "postgres_product_document":postgres_raw}


if __name__ == "__main__":
    try:
        options = image_options(os.environ)
        if sys.argv[1:] == ["--gateway-document"]:
            sys.stdout.buffer.write(gateway_document(options["images"]).content)
        elif sys.argv[1:] == ["--parent-website"]:
            from uuid import uuid4
            value = json.loads(os.environ["CPK_SOURCE_PARENT_WEBSITE"], object_pairs_hook=_unique)
            # A fresh PUBLIC lifecycle ID, never a key/credential. Persist the
            # output once; preparing again requires a separate owner decision.
            result = parent_website_input(options["images"], value, receiver_id=uuid4().hex)
            sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
        elif sys.argv[1:] == ["--child-postgres"]:
            from uuid import uuid4
            value = json.loads(os.environ["CPK_SOURCE_CHILD_POSTGRES"], object_pairs_hook=_unique)
            sys.stdout.buffer.write(child_postgres_document(options["images"], value, receiver_id=uuid4().hex).content)
        elif sys.argv[1:] == ["--sender"]:
            result = sender_input(os.environ["CPK_SOURCE_GATEWAY_DOCUMENT"], os.environ["CPK_SOURCE_POSTGRES_DOCUMENT"])
            sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
        elif sys.argv[1:]:
            raise ValueError("unknown public preparation mode")
    except Exception:
        print("source assembly image input refused", file=sys.stderr)
        raise SystemExit(2) from None
