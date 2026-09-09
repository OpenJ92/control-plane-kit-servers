"""Pure root bootstrap projection and its narrow public acquisition interface."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.runtime_effects import ImagePullAuthority
from control_plane_kit_core.runtime_authority import (
    RuntimeAuthorityAccessDeliveryCodec, RuntimeAuthorityReference,
)
from control_plane_kit_core.secrets import (
    SecretEnvironmentDelivery, SecretFileDelivery, SecretProviderEndpointReference,
    SecretReference, SecretUseIntent,
)
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology, validate_graph
from control_plane_kit_core.verification import HttpCheck

from .installation import (
    DockerCpkInstallation, ExternalInstallationIngress, compose_docker_cpk_installation,
)


MAX_BYTES = 1_048_576


class RootBootstrapError(ValueError):
    """Bounded public failure; never includes provider bodies or secret values."""


class RootBootstrapHold(RootBootstrapError):
    """Prior effects cannot safely be redispatched."""


def canonical(value: object) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError):
        raise RootBootstrapError("bootstrap document is invalid") from None
    if len(raw) > MAX_BYTES:
        raise RootBootstrapError("bootstrap document exceeds its bound")
    return raw


def decode_document(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result
    try:
        if len(raw) > MAX_BYTES:
            raise ValueError("size")
        value = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ValueError("object")
        canonical(value)
        return value
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise RootBootstrapError("bootstrap document is invalid") from None


def _closed(value, keys, optional=()):
    if not isinstance(value, dict) or not set(keys) <= set(value) <= set(keys) | set(optional):
        raise RootBootstrapError("bootstrap input fields are invalid")


def _text(value, limit=128):
    if not isinstance(value, str) or not value or len(value.encode()) > limit or any(ord(c) < 32 for c in value):
        raise RootBootstrapError("bootstrap text input is invalid")
    return value


def _image_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise RootBootstrapError("bootstrap driver image identity is invalid")
    return value


def matches_image_reference(expected: str, repo_digests: tuple[str, ...]) -> bool:
    """Match the exact pin, allowing only Docker Hub official-library spelling."""
    if not re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", expected):
        return False
    permitted = {expected}
    official = re.fullmatch(r"docker\.io/library/([a-z0-9]+(?:[._-][a-z0-9]+)*)@(sha256:[0-9a-f]{64})", expected)
    if official is not None:
        repository, digest = official.groups()
        permitted.update(f"{prefix}{repository}@{digest}" for prefix in ("", "library/", "docker.io/"))
    return any(reference in permitted for reference in repo_digests)


def _installation(document):
    _closed(document, {"schema", "installation", "host_binding", "setup"}, {"image_pull_credentials"})
    if document["schema"] != "cpk.root-bootstrap.input.v1":
        raise RootBootstrapError("bootstrap input schema is invalid")
    item = document["installation"]
    _closed(item, {"installation_id", "workspace_id", "runtime_authority", "runtime_access",
        "products", "references", "workspace_grants", "provider_endpoint_ref", "external_endpoint"})
    _closed(item["products"], {"cpk", "postgres", "secrets"})
    _closed(item["references"], {"control_credential", "postgres_password", "custody_root_key",
        "provider_credentials_document", "provider_client_credential", "provider_bootstrap_credential_ref"})
    grants = []
    for grant in item["workspace_grants"]:
        _closed(grant, {"workspace_id", "scopes"})
        grants.append(WorkspaceGrant(grant["workspace_id"], tuple(PolicyScope(s) for s in grant["scopes"])))
    products = {name: ProductDescriptorCodec().decode_document(value)
                for name, value in item["products"].items()}
    return DockerCpkInstallation(
        installation_id=item["installation_id"], workspace_id=item["workspace_id"],
        runtime_authority=RuntimeAuthorityReference(item["runtime_authority"]),
        runtime_access=RuntimeAuthorityAccessDeliveryCodec().decode(item["runtime_access"]),
        cpk_product=products["cpk"], postgres_product=products["postgres"], secrets_product=products["secrets"],
        workspace_grants=tuple(grants),
        provider_endpoint_ref=SecretProviderEndpointReference(item["provider_endpoint_ref"]),
        ingress=ExternalInstallationIngress(item["external_endpoint"]), connector_product=None,
        **{name: SecretReference(value) for name, value in item["references"].items()},
    )


def plan_root_bootstrap(document: Mapping[str, object], *, driver_image_id: str) -> dict:
    """Compile the shared definition without reading material or contacting Docker."""
    try:
        driver_image_id = _image_id(driver_image_id)
        document = decode_document(canonical(document))
        installation = _installation(document)
        binding = document["host_binding"]
        _closed(binding, {"address", "port"})
        if binding["address"] != "127.0.0.1" or type(binding["port"]) is not int or not 1024 <= binding["port"] <= 65535:
            raise RootBootstrapError("bootstrap host binding must be explicit loopback")
        setup = document["setup"]
        _closed(setup, {"workspace_name", "provider", "secret_references", "image_pull_authorities", "ingress_authorities"})
        _text(setup["workspace_name"])
        provider = setup["provider"]
        _closed(provider, {"provider_id", "allowed_reference_prefixes", "allowed_intents"})
        _text(provider["provider_id"])
        if not provider["allowed_reference_prefixes"] or not provider["allowed_intents"]:
            raise RootBootstrapError("bootstrap provider scope must be explicit")
        for reference in provider["allowed_reference_prefixes"]:
            if SecretReference(reference).provider_id.value != provider["provider_id"]:
                raise RootBootstrapError("bootstrap provider reference scope is invalid")
        for intent in provider["allowed_intents"]:
            SecretUseIntent(intent)
        for name in ("secret_references", "image_pull_authorities", "ingress_authorities"):
            if not isinstance(setup[name], list) or len(setup[name]) > 32:
                raise RootBootstrapError("bootstrap setup exceeds its bound")
        for item in setup["secret_references"]:
            _closed(item, {"reference", "allowed_intents"})
            SecretReference(item["reference"])
            for intent in item["allowed_intents"]:
                SecretUseIntent(intent)
        # These are existing public command payloads, never arbitrary route names.
        for item in setup["image_pull_authorities"]:
            _closed(item, {"registry", "credential_reference"}, {"repository"})
            ImagePullAuthority(item["registry"], item.get("repository"), SecretReference(item["credential_reference"]))
        for item in setup["ingress_authorities"]:
            _closed(item, {"authority_ref", "authority"})
            _closed(item["authority"], {"provider_kind", "account_id", "zone_id", "zone_name", "api_token_ref",
                "allowed_hostname_pattern", "generated_secret_provider_registration_id", "generated_secret_reference_prefix"})
            if item["authority"]["provider_kind"] != "cloudflare":
                raise RootBootstrapError("bootstrap ingress authority is unsupported")
            SecretReference(item["authority"]["api_token_ref"])
            SecretReference(item["authority"]["generated_secret_reference_prefix"])
            from control_plane_kit_operations.ingress_authorities import CloudflareZoneIngressAuthorityCodec
            CloudflareZoneIngressAuthorityCodec().decode(item["authority"])
        pulls = document.get("image_pull_credentials", {})
        if not isinstance(pulls, dict) or len(pulls) > 3:
            raise RootBootstrapError("bootstrap image pull inputs are invalid")
        for registry, reference in pulls.items():
            ImagePullAuthority(registry, None, SecretReference(reference))
        topology = compose_docker_cpk_installation(installation)
        graph = compile_topology(topology)
        if not validate_graph(graph).valid:
            raise RootBootstrapError("bootstrap graph is invalid")
        definition = hashlib.sha256(canonical(document)).hexdigest()
        labels = {"org.openj92.cpk.bootstrap": definition,
                  "org.openj92.cpk.installation": installation.installation_id}
        products = {child.block_id: child.implementation.document.product
                    for child in topology.root.children if hasattr(child, "block_id")}
        nodes = []
        required = set()
        for node_id, product in products.items():
            node = graph.node(node_id)
            name = f"{topology.root.network_name}-{node_id}"
            files = []
            for delivery in node.secret_deliveries:
                if isinstance(delivery, (SecretEnvironmentDelivery, SecretFileDelivery)):
                    required.add(delivery.reference.reference_id)
                if isinstance(delivery, SecretFileDelivery):
                    suffix = hashlib.sha256(delivery.target_path.encode()).hexdigest()[:16]
                    files.append({"name": f"{name}-file-{suffix}", "target": delivery.target_path,
                                  "reference": delivery.reference.reference_id})
            nodes.append({"node_id": node_id, "name": name, "aliases": [node_id],
                "image": product.image.execution_reference,
                "environment": node.non_secret_environment(), "secret_files": files,
                "http_checks": [{"check": check.descriptor(), "url": f"http://{node_id}:{next(port.container_port for port in product.runtime_contract.provider_ports if port.provider_socket == check.provider_socket)}{check.path}"}
                                for check in product.runtime_contract.verification.checks if isinstance(check, HttpCheck)],
                "local_docker_access": ({"socket": "/var/run/docker.sock", "supplementary_group": "inspected-socket-gid"}
                                        if node_id == installation.cpk_node_id else None),
                "data_volumes": [{"name": f"{name}-{mount.resource_id}", "target": mount.target_path}
                                 for mount in product.runtime_contract.retained_data_mounts]})
        plan = {"schema": "cpk.root-bootstrap.plan.v1", "input": document,
            "driver_image_id": driver_image_id, "graph": GraphDescriptorCodec().encode(graph),
            "resources": {"network": {"name": topology.root.network_name}, "labels": labels, "nodes": nodes},
            "required_material": sorted(required), "external_endpoint": installation.ingress.endpoint,
            "cpk_node_id": installation.cpk_node_id, "postgres_node_id": installation.postgres_node_id,
            "secrets_node_id": installation.secrets_node_id,
            "setup_bindings": {"ingress.generated_secret_provider_registration_id": "result-of-command.secret-provider.register"},
            "setup_routes": ["command.workspace.create", "command.secret-provider.register",
                *(["command.secret-reference.register"] * len(setup["secret_references"])),
                "command.runtime-authority.register", "command.runtime-authority-delivery.register",
                *(["command.product.import"] * len(document["installation"]["products"])),
                *(["command.image-pull-authority.register"] * len(setup["image_pull_authorities"])),
                *(["command.ingress-authority.register"] * len(setup["ingress_authorities"]))]}
        plan["digest"] = hashlib.sha256(canonical(plan)).hexdigest()
        return plan
    except RootBootstrapError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RootBootstrapError("bootstrap input could not be verified") from None


def verified_plan(plan, expected_digest, driver_image_id):
    _image_id(driver_image_id)
    if not isinstance(plan, dict) or plan.get("driver_image_id") != driver_image_id:
        raise RootBootstrapError("bootstrap driver image does not match the plan")
    try:
        expected = plan_root_bootstrap(plan["input"], driver_image_id=driver_image_id)
        if expected != plan or expected["digest"] != expected_digest:
            raise RootBootstrapError("bootstrap plan does not match reviewed intent")
        return expected
    except (KeyError, TypeError):
        raise RootBootstrapError("bootstrap plan could not be verified") from None


def apply_root_bootstrap(plan, *, expected_digest: str, driver_image_id: str,
                         index_path: Path, state_directory: Path) -> dict:
    plan = verified_plan(plan, expected_digest, driver_image_id)
    from .bootstrap_runtime import acquire_root
    return acquire_root(plan, Path(index_path), Path(state_directory))


def inspect_root_bootstrap(*, state_directory: Path) -> dict:
    from .bootstrap_runtime import inspect_root
    return inspect_root(Path(state_directory))
