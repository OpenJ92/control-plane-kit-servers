"""Public root pre-projection input; no keys, materials, plans or runtime IO."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import OciImageReferenceCodec, ProductDescriptorCodec, ProductReference, ProductReferenceCodec
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference, RuntimeAuthorityAccessDeliveryCodec
from control_plane_kit_core.secrets import SecretReference, SecretProviderEndpointReference
from control_plane_kit_core.receiver_configuration import ReceiverNodeControlConfigurationCodec
from control_plane_kit_servers_cpk_server.bootstrap import canonical, decode_document
from control_plane_kit_servers_cpk_server.installation import ControlAuthCodec, MultiPrincipalControlAuth
from control_plane_kit_servers_cpk_server.control_configuration import CpkSourceVariant, cpk_source_runtime_contract
from control_plane_kit_servers_cpk_server.managed_health_configuration import (
    MANAGED_HEALTH_ARTIFACT_ID, MANAGED_HEALTH_CONFIGURATION_PATH,
    _managed_health_configuration_from_artifact,
)
from control_plane_kit_servers_secrets_server.configuration import secrets_source_runtime_contract
from control_plane_kit_servers_cloudflared_connector.managed import declared_runtime_contract

ROOT = Path(__file__).resolve().parents[1]
SENDER_PATH = "/etc/cpk/cpk-server/managed-verification.json"


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("public root input is invalid")
        value[key] = item
    return value


def _frozen(raw, digest):
    if type(raw) is not str or sha256(raw.encode()).hexdigest() != digest:
        raise ValueError("public root input hash differs")
    return raw


def prepare_root_input(value):
    """Keep normal input/setup ownership; add reviewed public product values."""
    expected = {"base_input", "parent_public_document", "parent_public_sha256", "cpk_image",
        "secrets_image", "connector_image", "gateway_document", "gateway_sha256",
        "sender_document", "sender_sha256", "website", "capability_ids"}
    if type(value) is not dict or value.keys() != expected:
        raise ValueError("public root input is invalid")
    document = deepcopy(value["base_input"])
    item = document["installation"]
    # The material preparer owns the real commitment, after explicit role policy
    # and setup administration are frozen. Never invent one for actual inputs.
    if "workspace_authority" in item or "managed_health_configuration" in item or "website" in item:
        raise ValueError("public root input requires the unprojected base")
    # Empty legacy grants and no private commitment are intentional here. A
    # full DockerCpkInstallation would select static admission too early.
    # Decode public values only; Vale's real material projection constructs the
    # dynamic installation after computing its own commitment.
    if document["schema"] != "cpk.root-bootstrap.input.v1" or item["workspace_grants"] != []:
        raise ValueError("public root input requires empty unprojected grants")
    authority = RuntimeAuthorityReference(item["runtime_authority"])
    access = RuntimeAuthorityAccessDeliveryCodec().decode(item["runtime_access"])
    if access.authority_ref != authority:
        raise ValueError("public root runtime delivery differs")
    if not isinstance(ControlAuthCodec().decode(item["control_auth"]), MultiPrincipalControlAuth):
        raise ValueError("public root input requires explicit principal material reference")
    for reference in item["references"].values():
        SecretReference(reference)
    SecretProviderEndpointReference(item["provider_endpoint_ref"])
    codec, images = ProductDescriptorCodec(), OciImageReferenceCodec()
    stock = codec.decode_document((ROOT / "products/postgres_server/product.cpk.json").read_bytes())
    if codec.decode_document(item["products"]["postgres"]) != stock:
        raise ValueError("parent database must retain the root catalogue document")
    public_raw = _frozen(value["parent_public_document"], value["parent_public_sha256"])
    public = json.loads(public_raw, object_pairs_hook=_unique)
    if public["schema"] != "cpk.root-commissioning.public.v1":
        raise ValueError("parent public commissioning schema differs")
    receivers = []
    for role, owner, socket in (("cpk", cpk_source_runtime_contract, "http-api"),
            ("secrets", secrets_source_runtime_contract, "control")):
        artifact = ConfigurationArtifact.from_descriptor(public["artifacts"][role])
        control = ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode())
        target = control.target
        if (target.workspace_id.value != item["workspace_id"] or
                target.runtime_id.value != item["installation_id"] + "-docker" or
                target.node_id.value != item["installation_id"] + "-" + role or
                target.provider_socket_name.value != socket or
                target.receiver_id != public["receiver_ids"][role]):
            raise ValueError("parent public receiving scope differs")
        receivers.append(target.receiver_id)
        contract = owner(CpkSourceVariant.DOCKER_CLOUDFLARE, artifact) if role == "cpk" else owner(artifact)
        base = codec.decode_document(item["products"][role])
        item["products"][role] = json.loads(codec.encode_document(replace(base.product,
            image=images.decode(value[role + "_image"]), runtime_contract=contract)).content)
    gateway_raw = _frozen(value["gateway_document"], value["gateway_sha256"])
    gateway = codec.decode_document(gateway_raw.encode())
    sender_raw = _frozen(value["sender_document"], value["sender_sha256"])
    sender = json.loads(sender_raw, object_pairs_hook=_unique)
    if (sender.keys() != {"schema", "gateway_product", "postgres_product_document"} or
            sender["schema"] != "cpk-server.managed-verification.v1" or
            ProductReferenceCodec().decode(sender["gateway_product"]) != ProductReference.from_document(gateway)):
        raise ValueError("sender gateway binding differs")
    codec.decode_document(sender["postgres_product_document"].encode())
    website = deepcopy(value["website"])
    web_control = ReceiverNodeControlConfigurationCodec().decode_bytes(
        website["managed_control_configuration"]["content"].encode())
    target = web_control.target
    if (len(set(receivers)) != 2 or target.receiver_id in receivers or
            target.workspace_id.value != item["workspace_id"] or
            target.runtime_id.value != item["installation_id"] + "-docker" or
            target.node_id.value != item["installation_id"] + "-website" or
            target.provider_socket_name.value != "control"):
        raise ValueError("parent website receiving scope differs")
    item["website"] = website
    connector = codec.decode_document((ROOT / "products/cloudflared_connector/product.cpk.json").read_bytes())
    connector = codec.encode_document(replace(connector.product, image=images.decode(value["connector_image"]),
        runtime_contract=declared_runtime_contract()))
    health_raw = json.dumps({"schema":"cpk-server.managed-health.v2",
        "docker":{"socket_path":"/var/run/docker.sock", "request_timeout":5.0},
        "capability_ids":value["capability_ids"], "gateway_documents":[gateway_raw],
        "native_product_document":connector.content.decode()}, sort_keys=True, separators=(",", ":")).encode()
    # The convenience artifact factory intentionally admits static v1 only.
    # Use the established explicit dynamic admission path, as root projection
    # does after the real workspace intent is supplied by its owner.
    health_artifact = ConfigurationArtifact(MANAGED_HEALTH_ARTIFACT_ID,
        MANAGED_HEALTH_CONFIGURATION_PATH, ConfigurationMediaType.JSON, health_raw.decode())
    _managed_health_configuration_from_artifact(health_artifact, dynamic_workspace=True)
    item["managed_health_configuration"] = health_artifact.descriptor()
    cpk = codec.decode_document(item["products"]["cpk"])
    sender_artifact = ConfigurationArtifact("cpk-managed-verification", SENDER_PATH, ConfigurationMediaType.JSON, sender_raw)
    contract = cpk.product.runtime_contract
    item["products"]["cpk"] = json.loads(codec.encode_document(replace(cpk.product, runtime_contract=replace(contract,
        configuration_artifacts=(*contract.configuration_artifacts, sender_artifact),
        public_environment=(*contract.public_environment, PublicStaticEnvironmentBinding(
            "CPK_MANAGED_VERIFICATION_CONFIGURATION_FILE", SENDER_PATH))))).content)
    return document


if __name__ == "__main__":
    try:
        value = decode_document(os.environ["CPK_GRANDPARENT_PUBLIC_INPUTS"].encode())
        sys.stdout.buffer.write(canonical(prepare_root_input(value)))
    except Exception:
        print("public root preparation refused", file=sys.stderr)
        raise SystemExit(2) from None
