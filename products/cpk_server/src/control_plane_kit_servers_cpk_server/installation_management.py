"""Pure optional runtime management for the shared child installation recipe.

Caller-selected public receiver identities and trust are preserved. This module
does not issue keys, grant authority, supply tunnel tokens or schedule effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import control_plane_kit_core as core
from control_plane_kit_core.products import (
    ProductDescriptorCodec, ProductDescriptorDocument, ProductIdentity,
    ProductInstanceConfiguration, instantiate_product,
)
from control_plane_kit_core.receiver_configuration import select_receiver_node_control_configuration_artifact

if TYPE_CHECKING:
    from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import GatewayHealthTransitConfiguration
    from .installation import DockerCpkInstallation


_INVALID = "installation management configuration is invalid"


def _declared_product(document, name, contract):
    if (not isinstance(document, ProductDescriptorDocument)
            or document.product.identity != ProductIdentity("control-plane-kit", name, 1)
            or ProductDescriptorCodec().encode_document(document.product).content != document.content
            or document.product.runtime_contract != contract):
        raise ValueError(_INVALID)
    return document.product


def selected_managed_connector(document):
    """Admit the unchanged managed declaration, without instance token material."""
    from control_plane_kit_servers_cloudflared_connector.managed import declared_runtime_contract
    return _declared_product(document, "cloudflared-connector", declared_runtime_contract())


@dataclass(frozen=True, kw_only=True, repr=False)
class DockerCpkConnectorControl:
    """Associate caller-supplied receiver material with one intended ingress."""

    ingress_id: str
    configuration: core.ReceiverNodeControlConfiguration = field(repr=False)

    def __post_init__(self):
        from control_plane_kit_servers_cloudflared_connector.managed import control_configuration_artifact
        # Reuse the public reference and exact product configuration laws.
        core.RuntimeManagement("gateway", self.ingress_id)
        control_configuration_artifact(self.configuration)


@dataclass(frozen=True, kw_only=True, repr=False)
class DockerCpkManagement:
    """Complete public management inputs; no credential or execution authority."""

    gateway_product: ProductDescriptorDocument
    connector_product: ProductDescriptorDocument
    management_ingress: core.NamedPublicIngress
    runtime_management: core.RuntimeManagement
    gateway_control: core.ReceiverNodeControlConfiguration = field(repr=False)
    transit_trust: GatewayHealthTransitConfiguration = field(repr=False)
    connector_controls: tuple[DockerCpkConnectorControl, ...] = field(repr=False)

    def __post_init__(self):
        from control_plane_kit_servers_cpk_local_gateway.control_configuration import gateway_control_configuration_artifact
        from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import gateway_health_declared_runtime_contract
        from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import gateway_health_transit_configuration_artifact
        _declared_product(self.gateway_product, "cpk-local-gateway", gateway_health_declared_runtime_contract())
        selected_managed_connector(self.connector_product)
        gateway_control_configuration_artifact(self.gateway_control)
        gateway_health_transit_configuration_artifact(self.transit_trust)
        if (type(self.management_ingress) is not core.NamedPublicIngress
                or type(self.runtime_management) is not core.RuntimeManagement
                or self.management_ingress.ingress_id != self.runtime_management.management_ingress_id
                or self.transit_trust.gateway_target != self.gateway_control.target
                or type(self.connector_controls) is not tuple or len(self.connector_controls) != 3
                or any(type(item) is not DockerCpkConnectorControl for item in self.connector_controls)
                or len({item.ingress_id for item in self.connector_controls}) != 3):
            raise ValueError(_INVALID)


def _require_scope(configuration, value, node_id):
    target = configuration.target
    if (target.workspace_id.value != value.workspace_id
            or target.runtime_id.value != value.installation_id + "-docker"
            or target.node_id.value != node_id
            or target.provider_socket_name != configuration.declaration.surface.provider_socket_name):
        raise ValueError(_INVALID)


def management_ingresses(value: DockerCpkInstallation):
    """Bind the coherent group to this installation and its three exact roles."""
    from .client.frontend import _canonical_origin
    group = value.management
    if (type(group) is not DockerCpkManagement
            or type(value.ingress) is not core.NamedPublicIngress
            or value.website is None or type(value.website.ingress) is not core.NamedPublicIngress):
        raise ValueError(_INVALID)
    group.__post_init__()
    gateway_id = group.runtime_management.gateway_node_id
    ingresses = (value.ingress, value.website.ingress, group.management_ingress)
    nodes = {value.cpk_node_id, value.postgres_node_id, value.secrets_node_id, value.website_node_id}
    if (value.connector_product != group.connector_product
            or value.website.connector_product != group.connector_product
            or gateway_id in nodes
            or group.management_ingress.target != core.PublicIngressTarget(gateway_id, "control")
            or len({item.ingress_id for item in ingresses}) != 3
            or len({_canonical_origin("https://" + item.hostname) for item in ingresses}) != 3
            or len({item.connector_node_id for item in ingresses}) != 3
            or {item.connector_node_id for item in ingresses} & (nodes | {gateway_id})
            or {item.ingress_id for item in group.connector_controls} != {item.ingress_id for item in ingresses}):
        raise ValueError(_INVALID)
    _require_scope(group.gateway_control, value, gateway_id)
    controls = {item.ingress_id: item.configuration for item in group.connector_controls}
    for ingress in ingresses:
        _require_scope(controls[ingress.ingress_id], value, ingress.connector_node_id)
    return ingresses


def _route(value, node_id, contract, configuration):
    from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import gateway_health_target_binding
    _require_scope(configuration, value, node_id)
    route = gateway_health_target_binding(target_id=node_id, target=configuration.target,
        runtime_contract=contract, hostname=node_id)
    if route.declaration != configuration.declaration:
        raise ValueError(_INVALID)
    return route


def managed_children(value: DockerCpkInstallation, children):
    """Derive relay membership from the actual configured installation blocks."""
    from control_plane_kit_servers_cloudflared_connector.managed import control_configuration_artifact
    from control_plane_kit_servers_cpk_local_gateway.control_configuration import gateway_control_configuration_artifact
    from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
        gateway_health_relay_configuration_artifact, gateway_health_source_runtime_contract,
    )
    from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import gateway_health_transit_configuration_artifact
    group = value.management
    ingresses = management_ingresses(value)
    connector = selected_managed_connector(group.connector_product)
    controls = {item.ingress_id: item.configuration for item in group.connector_controls}
    connectors = [instantiate_product(connector, ingress.connector_node_id,
        ProductInstanceConfiguration(public_environment=connector.runtime_contract.public_environment,
            configuration_artifacts=(control_configuration_artifact(controls[ingress.ingress_id]),)))
        for ingress in ingresses]
    routes = []
    for block in (*children, *connectors):
        if not block.spec.control_surfaces:
            continue
        implementation = block.implementation
        artifact = select_receiver_node_control_configuration_artifact(
            artifacts=implementation.configuration.configuration_artifacts,
            environment=implementation.configuration.public_environment,
            control_surfaces=block.spec.control_surfaces)
        configuration = core.ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode())
        routes.append(_route(value, block.block_id, implementation.document.product.runtime_contract, configuration))
    # Require the explicitly selected server receivers, including managed Web.
    required = {value.cpk_node_id, value.secrets_node_id, value.postgres_node_id}
    if value.website.managed_control_configuration is not None:
        required.add(value.website_node_id)
    if not required.issubset({route.target.node_id.value for route in routes}):
        raise ValueError(_INVALID)
    gateway = group.gateway_product.product
    gateway_id = group.runtime_management.gateway_node_id
    routes.append(_route(value, gateway_id, gateway.runtime_contract, group.gateway_control))
    if len({route.target.receiver_id for route in routes}) != len(routes):
        raise ValueError(_INVALID)
    relay = core.ReceiverManagementRoutes(group.gateway_control.target, tuple(routes))
    trust = gateway_health_transit_configuration_artifact(group.transit_trust)
    targets = gateway_health_relay_configuration_artifact(relay)
    control = gateway_control_configuration_artifact(group.gateway_control)
    # Product-owned cross-artifact admission, without replacing its declaration.
    gateway_health_source_runtime_contract(trust, targets, control)
    return (*connectors, instantiate_product(gateway, gateway_id,
        ProductInstanceConfiguration(public_environment=gateway.runtime_contract.public_environment,
            configuration_artifacts=(trust, targets, control))))
