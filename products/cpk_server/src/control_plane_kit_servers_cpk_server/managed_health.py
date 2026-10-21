"""Operations-to-Interpreter managed health composition; no admission or stores."""
import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.node_control import NodeControlGraphReference, NodeControlGraphReferenceRole
from control_plane_kit_core.planning import (
    ManagementBootstrapStage, ObserveManagementBootstrap, ObserveNodeHealth, PlanGraphSide,
    WaitForHealthy, resolve_management_observation,
)
from control_plane_kit_core.receiver_configuration import (
    ReceiverNodeControlConfigurationCodec, select_receiver_node_control_configuration_artifact,
)
from control_plane_kit_core.runtime_management import GatewayTransitProtocol
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, validate_graph
from control_plane_kit_core.types import Protocol, RuntimeKind
from control_plane_kit_interpreters.probes.health_signing import HealthSigningContext, HealthSigningKey
from control_plane_kit_interpreters.probes.health_transport import GatewayHealthTransportCode, SelectedManagementGateway
from control_plane_kit_operations.graph_authoring import product_reference_in_node
from control_plane_kit_operations.health_receiver_trust import HealthReceiverSelection
from control_plane_kit_operations.runtime_management_targets import (
    is_native_connection_operation, is_signed_management_health_operation, project_management_health_target,
)
from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
    ARTIFACT_ID as TARGETS_ARTIFACT_ID, CONFIGURATION_PATH as TARGETS_PATH,
)
from .health_receiver_adapters import select_own_health_configuration, select_gateway_health_route_binding

if TYPE_CHECKING:
    from .managed_health_placement import DockerRuntimeClientSelector


class ManagedHealthUnavailable(RuntimeError):
    """Fixed composition refusal; Operations records the failed read."""


def _product(products, workspace, node):
    reference = product_reference_in_node(node)
    values = tuple(value for value in products if value.workspace_id == workspace and value.reference == reference)
    if reference is None or len(values) != 1:
        raise ValueError
    return values[0]


def _authority(authorities, runtime, workspace=None):
    values = tuple(value for value in authorities if value.authority_ref == runtime.authority_ref
        and value.runtime_kind is runtime.kind and (workspace is None or value.workspace_id == workspace))
    if len(values) != 1:
        raise ValueError
    return values[0]


def _graph_pair(current, desired):
    pair = validate_graph(current), validate_graph(desired)
    for graph in pair:
        graph.require_valid()
    return pair


def _selection(product, node, artifact, socket, preparation, side):
    context = preparation.request.authority_context
    return HealthReceiverSelection(preparation.workspace_id, context.authored_graph_id,
        context.realized_projection_id, side, node.node_id, node.runtime_id, socket,
        product.reference, product.descriptor_document, artifact)


def _own_selection(products, graph, node_id, preparation, side):
    node = graph.node(node_id)
    product = _product(products, preparation.workspace_id, node)
    artifact = select_receiver_node_control_configuration_artifact(
        artifacts=node.configuration_artifacts,
        environment=node.public_environment + node.socket_environment,
        control_surfaces=node.block_spec.control_surfaces)
    configured = ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode("utf-8"))
    return _selection(product, node, artifact, configured.target.provider_socket_name.value, preparation, side)


@dataclass(frozen=True, slots=True, repr=False)
class ManagedHealthBridge:
    reader: object
    provider_clients: "DockerRuntimeClientSelector"
    endpoints: object | None
    decoders: object
    native: object | None = None

    def __post_init__(self):
        from .managed_health_placement import DockerRuntimeClientSelector

        if (type(self.provider_clients) is not DockerRuntimeClientSelector
                or (self.native is not None
                    and getattr(self.native, "provider_clients", None) is not self.provider_clients)):
            raise ValueError("managed provider composition is invalid")

    def select(self, *, plan, current, desired, registered_products, runtime_authorities):
        selected = None
        try:
            pair = _graph_pair(current, desired)
            result, required_native = [], []
            for activity in plan.activities:
                operation = activity.operation
                if type(operation) is WaitForHealthy:
                    return None
                if type(operation) not in (ObserveManagementBootstrap, ObserveNodeHealth):
                    continue
                resolved = resolve_management_observation(operation, *pair,
                    expected_operation=plan.activity(activity.activity_id).operation)
                graph = resolved.selected_graph.graph
                runtime = graph.runtimes[operation.target.runtime_id]
                authority = _authority(runtime_authorities, runtime)
                binding = self.provider_clients.select(workspace_id=authority.workspace_id,
                    runtime_id=runtime.runtime_id, authority=authority)
                if runtime.kind is not RuntimeKind.DOCKER or binding is None:
                    return None
                if (type(operation) is ObserveManagementBootstrap
                        and operation.stage is ManagementBootstrapStage.GATEWAY_LOCAL_READY
                        and (self.endpoints is None or self.endpoints.select(
                            provider_binding=binding, workspace_id=authority.workspace_id,
                            runtime_id=runtime.runtime_id, authority=authority) is None)):
                    return None
                gateway = _product(registered_products, authority.workspace_id, resolved.gateway_node)
                self.decoders.binding_for(gateway.reference, DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT)
                if is_native_connection_operation(operation):
                    required_native.append(activity.activity_id)
                elif is_signed_management_health_operation(operation):
                    project_management_health_target(plan, activity.activity_id, operation, *pair)
                else:
                    return None
                result.append(activity.activity_id)
            if required_native:
                if self.native is None:
                    return None
                supported = self.native.select(plan=plan, current=current, desired=desired,
                    registered_products=registered_products, runtime_authorities=runtime_authorities)
                if type(supported) is not tuple or supported != tuple(required_native):
                    return None
            selected = tuple(result)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            selected = None
        return selected

    async def observe_connection(self, realization, request, authority):
        selected = self.select(plan=realization.plan,
            current=DEFAULT_GRAPH_CODEC.decode(realization.base_graph.graph_descriptor),
            desired=DEFAULT_GRAPH_CODEC.decode(realization.desired_graph.graph_descriptor),
            registered_products=realization.registered_products, runtime_authorities=realization.runtime_authorities)
        if (selected is None or request.activity_id not in selected or self.native is None
                or not is_native_connection_operation(request.operation)):
            raise ManagedHealthUnavailable("managed health is unavailable")
        return await self.native.observe_connection(realization, request, authority)

    async def observe_signed(self, realization, request, authority):
        inputs = None
        try:
            preparation = authority.preparation
            if (preparation.workspace_id != request.source.workspace_id
                    or not is_signed_management_health_operation(request.operation)):
                raise ValueError
            current = DEFAULT_GRAPH_CODEC.decode(realization.base_graph.graph_descriptor)
            desired = DEFAULT_GRAPH_CODEC.decode(realization.desired_graph.graph_descriptor)
            selected = self.select(plan=realization.plan, current=current, desired=desired,
                registered_products=realization.registered_products, runtime_authorities=realization.runtime_authorities)
            if selected is None or request.activity_id not in selected:
                raise ValueError
            pair = _graph_pair(current, desired)
            projected = project_management_health_target(realization.plan, request.activity_id,
                request.operation, *pair)
            side = request.operation.target.graph_side
            graph = pair[0 if side is PlanGraphSide.BASE_GRAPH else 1].graph
            runtime = graph.runtimes[request.operation.target.runtime_id]
            selected_authority = _authority(realization.runtime_authorities, runtime, preparation.workspace_id)
            if selected_authority.authority_ref != request.authority_ref:
                raise ValueError
            own = _own_selection(realization.registered_products, graph, projected.target_node_id, preparation, side)
            configured = select_own_health_configuration(own)
            if (configured.target != preparation.request.target
                    or configured.declaration.identity() != preparation.request.declaration_identity):
                raise ValueError
            gateway = graph.node(projected.gateway_node_id)
            gateway_product = _product(realization.registered_products, preparation.workspace_id, gateway)
            gateway_configuration = select_own_health_configuration(_own_selection(
                realization.registered_products, graph, gateway.node_id, preparation, side))
            if gateway_configuration.target != preparation.transit_grant.gateway_target:
                raise ValueError
            socket_name = gateway_configuration.target.provider_socket_name.value
            sockets = tuple(value for value in gateway.sockets.providers if value.name == socket_name)
            ports = tuple(value.container_port for value in gateway_product.descriptor_document.product.runtime_contract.provider_ports
                if value.provider_socket == socket_name)
            if len(sockets) != 1 or sockets[0].protocol != Protocol.HTTP or len(ports) != 1:
                raise ValueError
            context = HealthSigningContext(preparation.request, preparation.transit_grant.attempt_id,
                gateway_configuration.target, configured.declaration,
                preparation.transit_grant.issuer, preparation.workload_grant.issuer)
            destination = None
            local = (type(request.operation) is ObserveManagementBootstrap
                and request.operation.stage is ManagementBootstrapStage.GATEWAY_LOCAL_READY)
            if not local:
                artifacts = tuple(value for value in gateway.configuration_artifacts
                    if value.artifact_id == TARGETS_ARTIFACT_ID and value.target_path == TARGETS_PATH)
                if len(artifacts) != 1:
                    raise ValueError
                targets = _selection(gateway_product, gateway, artifacts[0],
                    projected.gateway_transit_provider_socket_name, preparation, side)
                binding = select_gateway_health_route_binding(targets=targets, configured=configured,
                    gateway_configured=gateway_configuration)
                destination = SelectedManagementGateway(projected.ingress,
                    NodeControlGraphReference(NodeControlGraphReferenceRole.NODE, gateway.node_id),
                    projected.gateway_transit_provider_socket_name, configured.target.runtime_id,
                    binding.target_id, GatewayTransitProtocol.RECEIVER_HEALTH_READ_V2)
            inputs = pair, selected_authority, gateway, socket_name, ports[0], context, local, destination
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            inputs = None
        if inputs is None:
            raise ManagedHealthUnavailable("managed health is unavailable")
        pair, selected_authority, gateway, socket_name, port, context, local, destination = inputs
        # Only local readiness needs private placement; public reads use NamedIngress.
        endpoint = None
        if local:
            binding = self.provider_clients.select(workspace_id=preparation.workspace_id,
                runtime_id=request.operation.target.runtime_id, authority=selected_authority)
            if binding is None:
                raise ManagedHealthUnavailable("managed health is unavailable")
            endpoint = await asyncio.to_thread(self.endpoints.read,
                provider_binding=binding,
                workspace_id=preparation.workspace_id, runtime_id=request.operation.target.runtime_id,
                authority=selected_authority, gateway_node_id=gateway.node_id, socket_name=socket_name,
                port=port, graph_id=preparation.request.authority_context.authored_graph_id)
        observed = await self.reader.observe(request, plan=realization.plan, current=pair[0], desired=pair[1],
            authority_context=preparation.request.authority_context, context=context,
            transit_grant=preparation.transit_grant, workload_grant=preparation.workload_grant,
            transit_key=HealthSigningKey(authority.transit.public_key, authority.transit.resolution_grant),
            workload_key=HealthSigningKey(authority.workload.public_key, authority.workload.resolution_grant),
            destination=destination, local_destination=endpoint if local else None)
        return observed.result if getattr(observed, "code", None) is GatewayHealthTransportCode.RECEIVED else None


@dataclass(frozen=True, slots=True, repr=False)
class ManagedHealthBootstrap:
    """Trusted process composition, never public product-registration authority.

    Scoped SDK clients are caller-owned. Native support is explicit;
    public_client is an explicit ingress transport override for maintained tests.
    Local readiness always uses the real bounded socket transport.
    """
    gateway_documents: tuple
    provider_clients: "DockerRuntimeClientSelector"
    endpoints: object | None = None
    native: object | None = None
    public_client: object | None = None

    def build(self, authorized_secret_resolver):
        import time
        from control_plane_kit_interpreters.docker.managed_health import DockerManagedHealthReader
        from control_plane_kit_interpreters.probes.health_signing import Ed25519HealthCredentialPairSigner
        from control_plane_kit_interpreters.probes.health_transport import SignedGatewayHealthClient
        from control_plane_kit_interpreters.probes.local_health import LocalGatewayHealthClient
        from .health_receiver_adapters import health_receiver_decoders
        if authorized_secret_resolver is None:
            raise ManagedHealthUnavailable("managed health requires an authorized secret resolver")
        clock = lambda: int(time.time())
        reader = DockerManagedHealthReader(
            Ed25519HealthCredentialPairSigner(authorized_secret_resolver, clock),
            self.public_client if self.public_client is not None else SignedGatewayHealthClient(clock=clock),
            LocalGatewayHealthClient(clock=clock))
        return ManagedHealthBridge(reader, self.provider_clients, self.endpoints,
            health_receiver_decoders(gateway_documents=self.gateway_documents), self.native)
