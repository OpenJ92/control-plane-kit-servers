"""Pure frontend values for Servers #243; no build, bootstrap or provider IO.

Interprets web221ad6dbb409f7765517b7b4efbfdab040b65544's serving interface,
not its packaging JSON as a second CPK wire format. Image provenance and actual
workspace/host isolation are reviewed by the caller before public submission.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from urllib.parse import urlsplit

from control_plane_kit_core.algebra import (
    BlockSockets, DeploymentTopology, DockerRuntime, ProviderSocket,
)
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import (
    ContainerServerProduct, OciImageReference, ProductDescriptorCodec,
    ProductDescriptorDocument, ProductIdentity, ProductInstanceConfiguration,
    ProductRuntimeContract, ProductRuntimeContractCodec, ProviderRuntimePort,
    instantiate_product,
)
from control_plane_kit_core.public_ingress import NamedPublicIngress
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.types import Protocol


_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_COORDINATE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\Z")


def _canonical_origin(value: str) -> str:
    """Accept bounded ASCII DNS/canonical IP origins without normalizing input.

    Reject WHATWG numeric-host aliases and explicit default ports so the Node
    host does not silently select a different origin. DNS names use ordinary
    labels without IDNA A-labels; this is an authoring subset, not an IDNA or
    WHATWG implementation. The web process remains the final URL validator.
    """
    try:
        if (type(value) is not str or not 1 <= len(value) <= 2048 or "%" in value
                or any(ord(c) < 33 or ord(c) > 126 for c in value)):
            raise ValueError
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (parsed.scheme != "https" or not host or parsed.username is not None
                or parsed.password is not None or parsed.path or parsed.query or parsed.fragment):
            raise ValueError
        if ":" in host:
            canonical_host = "[" + ipaddress.IPv6Address(host).compressed + "]"
        else:
            try:
                canonical_host = str(ipaddress.IPv4Address(host))
            except ValueError:
                labels = host.removesuffix(".").split(".")
                if (len(host) > 253 or not all(_DNS_LABEL.fullmatch(label)
                                              and not label.startswith("xn--") for label in labels)
                        or labels[-1].isdigit() or re.fullmatch(r"0x[0-9a-f]*", labels[-1])):
                    raise ValueError
                canonical_host = host
        if port is not None and not 1 <= port <= 65535:
            raise ValueError
        suffix = "" if port in (None, 443) else f":{port}"
        if value != f"https://{canonical_host}{suffix}":
            raise ValueError
        return value
    except (TypeError, ValueError):
        raise ValueError("frontend upstream must be a canonical HTTPS origin") from None


def frontend_product(
    image: OciImageReference, *, upstream: str, port: int = 8080,
) -> ContainerServerProduct:
    """Describe the reviewed web process using an explicitly supplied image.

    This does not attest that the pinned image was built, published or reviewed.
    Empty verification means website readiness is unverified, never healthy.
    """
    if not isinstance(image, OciImageReference):
        raise TypeError("frontend requires an explicit immutable OCI image")
    upstream = _canonical_origin(upstream)
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("frontend port must be an integer from 1024 to 65535")
    contract = ProductRuntimeContract(
        sockets=BlockSockets(providers=(ProviderSocket("http", Protocol.HTTP),)),
        provider_ports=(ProviderRuntimePort("http", port),),
        public_environment=(PublicStaticEnvironmentBinding("CPK_WEB_UPSTREAM", upstream),
                            PublicStaticEnvironmentBinding("PORT", str(port))),
    )
    material = {"image": image.descriptor(),
                "runtime_contract": ProductRuntimeContractCodec().encode(contract)}
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    return ContainerServerProduct(
        ProductIdentity("control-plane-kit-web", f"website-{digest}", 1), image, contract,
        display_name="CPK website",
        description="Topology viewer and plan approval website. Readiness is unverified.",
    )


def compose_frontend_deployment(
    *, image: OciImageReference, upstream: str, workspace_id: str,
    runtime_id: str, network_name: str, authority_ref: RuntimeAuthorityReference,
    ingress: NamedPublicIngress, connector_product: ProductDescriptorDocument,
    port: int = 8080,
) -> DeploymentTopology:
    """Return only the website and connector in an explicit nonmanaged runtime.

    ``workspace_id`` labels the topology; the caller must separately select this
    workspace in the public API. A graph name is not an authorization boundary.
    Keeping that workspace outside Hello teardown preserves frontend lifetime;
    this function does not discover existing resources or grant retention.
    """
    for value in (workspace_id, runtime_id, network_name):
        if type(value) is not str or not _COORDINATE.fullmatch(value):
            raise ValueError("frontend deployment coordinates must be bounded identifiers")
    if not isinstance(authority_ref, RuntimeAuthorityReference):
        raise TypeError("frontend placement requires a runtime authority reference")
    if not isinstance(ingress, NamedPublicIngress):
        raise TypeError("frontend requires an explicit named public ingress")
    if (ingress.target.provider_socket != "http"
            or ingress.target.node_id == ingress.connector_node_id):
        raise ValueError("frontend ingress must target the distinct website HTTP socket")
    if not isinstance(connector_product, ProductDescriptorDocument):
        raise TypeError("frontend requires a selected connector descriptor")
    connector = connector_product.product
    if (ProductDescriptorCodec().encode_document(connector).content != connector_product.content
            or connector.identity != ProductIdentity("control-plane-kit", "cloudflared-connector", 1)
            or connector.runtime_contract != ProductRuntimeContract()):
        raise ValueError("frontend requires the ordinary selected connector contract")
    website = frontend_product(image, upstream=upstream, port=port)
    children = tuple(instantiate_product(product, node_id,
                         ProductInstanceConfiguration.from_contract(product.runtime_contract))
                     for product, node_id in ((website, ingress.target.node_id),
                                              (connector, ingress.connector_node_id)))
    return DeploymentTopology(
        workspace_id,
        DockerRuntime(runtime_id=runtime_id, network_name=network_name,
                      authority_ref=authority_ref, children=children),
        public_ingresses=(ingress,),
    )
