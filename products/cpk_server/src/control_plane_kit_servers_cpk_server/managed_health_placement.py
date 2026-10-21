"""Explicit provisioner coordinates plus current Interpreter-owned Docker reads.

This module does not discover, create, attach or certify a route. Configured
clients are caller-owned and must address the admitted local Docker authority.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from ipaddress import ip_address
import re

from control_plane_kit_core.probe_intents import EndpointContext, LiteralEndpointMaterial, RuntimeEndpointObservation
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.types import Protocol, RuntimeKind
from control_plane_kit_interpreters.docker import DockerSdkClient, DockerSdkResourceInspection
from control_plane_kit_interpreters.probes.local_health import SelectedLocalGateway
from control_plane_kit_interpreters.probes.security import ProbeAddressPolicy
from control_plane_kit_operations.runtime_authorities import (
    LocalDockerSocketAuthority, RegisteredRuntimeAuthority, RegisteredRuntimeAuthorityStatus,
)


class GatewayPlacementUnavailable(RuntimeError):
    """Fixed failure with no provider response, address or binding material."""


def _identity(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _reference(value):
    return type(value) is str and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}", value) is not None


@dataclass(frozen=True, slots=True, repr=False)
class DockerRuntimeClientBinding:
    """Exact configured capability; the caller owns the client and its transport."""
    workspace_id: str
    runtime_id: str
    authority_ref: RuntimeAuthorityReference
    client: DockerSdkClient = field(repr=False, compare=False)

    def __post_init__(self):
        if (not all(_reference(value) for value in (self.workspace_id, self.runtime_id))
                or type(self.authority_ref) is not RuntimeAuthorityReference
                or type(self.client) is not DockerSdkClient):
            raise ValueError("runtime client binding is invalid")


@dataclass(frozen=True, slots=True, repr=False)
class DockerRuntimeClientSelector:
    bindings: tuple[DockerRuntimeClientBinding, ...]

    def __post_init__(self):
        if (type(self.bindings) is not tuple or len(self.bindings) > 64
                or any(type(value) is not DockerRuntimeClientBinding for value in self.bindings)):
            raise ValueError("runtime client selection is invalid")
        seen = set()
        for value in self.bindings:
            value.__post_init__()
            scope = (value.workspace_id, value.runtime_id, value.authority_ref)
            if scope in seen:
                raise ValueError("runtime client selection is invalid")
            seen.add(scope)

    def select(self, *, workspace_id, runtime_id, authority):
        # Configured capability only: no provider connection or transport proof.
        if (type(authority) is not RegisteredRuntimeAuthority
                or authority.workspace_id != workspace_id
                or authority.status is not RegisteredRuntimeAuthorityStatus.ACTIVE
                or authority.runtime_kind is not RuntimeKind.DOCKER
                or type(authority.authority) is not LocalDockerSocketAuthority):
            return None
        values = tuple(value for value in self.bindings
            if (value.workspace_id, value.runtime_id, value.authority_ref)
                == (workspace_id, runtime_id, authority.authority_ref))
        return values[0] if len(values) == 1 else None


@dataclass(frozen=True, slots=True, repr=False)
class DockerControllerPlacement:
    provider: DockerRuntimeClientBinding
    controller_container_id: str

    def __post_init__(self):
        if (type(self.provider) is not DockerRuntimeClientBinding
                or not _identity(self.controller_container_id)):
            raise ValueError("controller placement configuration is invalid")
        self.provider.__post_init__()


@dataclass(frozen=True, slots=True, repr=False)
class DockerGatewayBinding:
    workspace_id: str
    runtime_id: str
    authority_ref: RuntimeAuthorityReference
    gateway_node_id: str
    network_id: str
    gateway_container_id: str

    def __post_init__(self):
        if (not all(_reference(value) for value in (self.workspace_id, self.runtime_id, self.gateway_node_id))
                or type(self.authority_ref) is not RuntimeAuthorityReference
                or not all(_identity(value) for value in (self.network_id, self.gateway_container_id))):
            raise ValueError("gateway binding configuration is invalid")


@dataclass(frozen=True, slots=True, repr=False)
class DockerGatewayEndpointReader:
    placements: tuple[DockerControllerPlacement, ...]
    binding_for: Callable

    def __post_init__(self):
        if (type(self.placements) is not tuple or len(self.placements) > 64
                or any(type(value) is not DockerControllerPlacement for value in self.placements)
                or not callable(self.binding_for)):
            raise ValueError("gateway endpoint composition is invalid")
        for value in self.placements:
            value.__post_init__()

    def select(self, *, provider_binding, workspace_id, runtime_id, authority):
        # No inspection or binding lookup before the owner records its attempt.
        if (type(provider_binding) is not DockerRuntimeClientBinding
                or type(authority) is not RegisteredRuntimeAuthority
                or authority.workspace_id != workspace_id
                or authority.status is not RegisteredRuntimeAuthorityStatus.ACTIVE
                or authority.runtime_kind is not RuntimeKind.DOCKER
                or type(authority.authority) is not LocalDockerSocketAuthority
                or (provider_binding.workspace_id, provider_binding.runtime_id, provider_binding.authority_ref)
                    != (workspace_id, runtime_id, authority.authority_ref)):
            return None
        values = tuple(value for value in self.placements
            if value.provider is provider_binding)
        return values[0] if len(values) == 1 else None

    def read(self, *, provider_binding, workspace_id, runtime_id, authority, gateway_node_id, socket_name, port, graph_id):
        selected = None
        try:
            placement = self.select(provider_binding=provider_binding,
                workspace_id=workspace_id, runtime_id=runtime_id, authority=authority)
            if placement is None or type(port) is not int or not 1 <= port <= 65535:
                raise ValueError
            binding = self.binding_for(workspace_id=workspace_id, runtime_id=runtime_id,
                authority_ref=authority.authority_ref, gateway_node_id=gateway_node_id)
            if type(binding) is not DockerGatewayBinding:
                raise ValueError
            binding.__post_init__()
            if ((binding.workspace_id, binding.runtime_id, binding.authority_ref, binding.gateway_node_id)
                    != (workspace_id, runtime_id, authority.authority_ref, gateway_node_id)):
                raise ValueError
            client = provider_binding.client
            network = client.inspect_network(binding.network_id)
            controller = client.inspect_container(placement.controller_container_id)
            gateway = client.inspect_container(binding.gateway_container_id)
            if (type(network) is not DockerSdkResourceInspection or network.network_id != binding.network_id
                    or type(controller) is not DockerSdkResourceInspection
                    or controller.container_id != placement.controller_container_id or not controller.running
                    or type(gateway) is not DockerSdkResourceInspection
                    or gateway.container_id != binding.gateway_container_id or not gateway.running):
                raise ValueError
            for observed in (controller, gateway):
                if type(observed.network_attachments) is not tuple:
                    raise ValueError
                members = tuple(value for value in observed.network_attachments if value.network_id == binding.network_id)
                if len(members) != 1:
                    raise ValueError
            address = members[0].private_address  # Last inspected membership is the gateway's.
            if address is None:
                raise ValueError
            numeric = ip_address(address)
            if numeric.is_unspecified or numeric.is_multicast or numeric.is_loopback:
                raise ValueError
            host = f"[{numeric}]" if numeric.version == 6 else str(numeric)
            origin = f"http://{host}:{port}"
            selected = SelectedLocalGateway(RuntimeEndpointObservation(gateway_node_id, socket_name,
                graph_id, Protocol.HTTP, EndpointContext.RUNTIME_PRIVATE,
                LiteralEndpointMaterial(origin)),
                ProbeAddressPolicy(runtime_private_authorities=frozenset({origin})))
        except Exception:
            selected = None
        if selected is None:
            # Raise outside the provider exception context; retain no provider data.
            raise GatewayPlacementUnavailable("gateway placement is unavailable")
        return selected
