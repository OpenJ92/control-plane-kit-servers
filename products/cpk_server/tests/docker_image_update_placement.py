"""Owned controller membership and provider observations for #251, no scheduler."""
from datetime import datetime, timezone

from control_plane_kit_core.planning import StartRuntime
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
from control_plane_kit_operations.effect_outcome_evidence import NativeConnectionObservation, NativeConnectionOutcome
from control_plane_kit_operations.runtime_management_targets import is_native_connection_operation
from control_plane_kit_servers_cpk_server.managed_health_placement import (
    DockerControllerPlacement, DockerGatewayBinding, DockerGatewayEndpointReader,
)

from docker_image_update_material import IMAGES
from docker_image_update_ports import FixtureBoundaryFailure


PREFIX = "org.openj92.cpk."


class OwnedControllerPlacement:
    def __init__(self, engine, sdk, workspace, controller_id, daemon_id):
        self.engine, self.sdk, self.workspace = engine, sdk, workspace
        self.controller_id, self.daemon_id = controller_id, daemon_id
        self.network_id = None
        self.nodes, self.bindings = {}, {}
        self.attachment_attempted = False
        self.reader = DockerGatewayEndpointReader((DockerControllerPlacement(workspace, "docker",
            RuntimeAuthorityReference("local-docker"), controller_id, sdk),), self.binding_for)

    def same_daemon(self):
        if self.engine.info().get("ID") != self.daemon_id:
            raise FixtureBoundaryFailure("fixture daemon identity changed")

    def owned(self, labels, kind, node=None):
        expected = {PREFIX + "workspace": self.workspace, PREFIX + "runtime": "docker",
            PREFIX + "kind": kind}
        if node is not None:
            expected[PREFIX + "node"] = node
        if any(labels.get(key) != value for key, value in expected.items()):
            raise FixtureBoundaryFailure("provider resource ownership differs")

    def binding_for(self, *, workspace_id, runtime_id, authority_ref, gateway_node_id):
        if (workspace_id, runtime_id, authority_ref.reference_id, gateway_node_id) != (
                self.workspace, "docker", "local-docker", "gateway"):
            raise FixtureBoundaryFailure("gateway binding scope differs")
        return self.bindings.get("gateway")

    def completed(self, record):
        self.same_daemon()
        request, result = record.request, record.result
        if (request.source.workspace_id != self.workspace
                or request.authority_ref != RuntimeAuthorityReference("local-docker")
                or result.evidence.get("runtime_id") != "docker"):
            raise FixtureBoundaryFailure("runtime effect placement scope differs")
        if type(request.operation) is StartRuntime:
            network = self.engine.networks.get(result.evidence["network"])
            self.owned(network.attrs["Labels"], "runtime-network")
            observed = self.sdk.inspect_network(network.id)
            if observed is None or observed.network_id != network.id:
                raise FixtureBoundaryFailure("returned network name has no exact identity")
            if self.network_id is not None and self.network_id != network.id:
                raise FixtureBoundaryFailure("runtime network identity changed")
            self.network_id = network.id
            controller = self.sdk.inspect_container(self.controller_id)
            if controller is None or controller.container_id != self.controller_id or not controller.running:
                raise FixtureBoundaryFailure("owned controller is unavailable")
            memberships = [item for item in controller.network_attachments if item.network_id == network.id]
            if self.attachment_attempted:
                if len(memberships) != 1:
                    raise FixtureBoundaryFailure("prior fixture attachment is uncertain")
                return
            if memberships:
                raise FixtureBoundaryFailure("controller had an undeclared existing attachment")
            self.attachment_attempted = True
            network.connect(self.controller_id)
            fresh = self.sdk.inspect_container(self.controller_id)
            if fresh is None or sum(item.network_id == network.id for item in fresh.network_attachments) != 1:
                raise FixtureBoundaryFailure("controller attachment was not observed")
            return
        name = request.operation.target.node_id
        container = self.engine.containers.get(result.evidence["container"])
        self.owned(container.labels, "container", name)
        self.nodes[name] = container.id
        self.inspect_node(name)
        if name == "gateway":
            self.bindings[name] = DockerGatewayBinding(self.workspace, "docker",
                RuntimeAuthorityReference("local-docker"), name, self.network_id, container.id)

    def inspect_node(self, name, *, image_role=None):
        self.same_daemon()
        container = self.engine.containers.get(self.nodes[name])
        self.owned(container.labels, "container", name)
        observed = self.sdk.inspect_container(container.id)
        role = image_role or (name if name in {"gateway", "connector"} else "hello_a")
        if (observed is None or observed.container_id != container.id or not observed.running
                or container.attrs["Image"] != IMAGES[role]["image_id"]
                or container.attrs["Config"]["User"] != IMAGES[role]["user"]
                or sum(item.network_id == self.network_id for item in observed.network_attachments) != 1):
            raise FixtureBoundaryFailure("installed node identity differs")
        return observed

    def detach(self):
        self.same_daemon()
        if self.network_id is None:
            return
        network = self.engine.networks.get(self.network_id)
        self.owned(network.attrs["Labels"], "runtime-network")
        observed = self.sdk.inspect_container(self.controller_id)
        if observed is None:
            raise FixtureBoundaryFailure("controller missing before detach")
        if any(item.network_id == self.network_id for item in observed.network_attachments):
            if not self.attachment_attempted:
                raise FixtureBoundaryFailure("refusing unrecorded attachment removal")
            network.disconnect(self.controller_id)
        fresh = self.sdk.inspect_container(self.controller_id)
        if fresh is None or any(item.network_id == self.network_id for item in fresh.network_attachments):
            raise FixtureBoundaryFailure("controller detachment is uncertain")


class SyntheticConnectorConnection:
    """Synthetic CONNECTED, correlated with an actual owned pause container."""
    def __init__(self, placement, ingress):
        self.placement, self.ingress = placement, ingress
        self.reads = []

    def select(self, *, plan, current, desired, registered_products, runtime_authorities):
        graph = desired if desired.nodes else current
        connector = graph.node("connector")
        if connector.metadata.get("oci_image") != IMAGES["connector"]["reference"]:
            return None
        authorities = [value for value in runtime_authorities if value.workspace_id == self.placement.workspace
            and value.authority_ref == RuntimeAuthorityReference("local-docker")]
        if len(authorities) != 1:
            return None
        required = tuple(value.activity_id for value in plan.activities
            if is_native_connection_operation(value.operation))
        return required

    async def observe_connection(self, realization, request, authority):
        selected = self.select(plan=realization.plan,
            current=DEFAULT_GRAPH_CODEC.decode(realization.base_graph.graph_descriptor),
            desired=DEFAULT_GRAPH_CODEC.decode(realization.desired_graph.graph_descriptor),
            registered_products=realization.registered_products,
            runtime_authorities=realization.runtime_authorities)
        if (selected is None or request.activity_id not in selected or not self.ingress.allocations
                or authority.authority_ref != request.authority_ref
                or request.source.workspace_id != self.placement.workspace):
            raise FixtureBoundaryFailure("synthetic native scope differs")
        connector = self.placement.inspect_node("connector")
        instant = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.reads.append((request.effect_id, request.activity_id.value, connector.container_id))
        return NativeConnectionObservation(NativeConnectionOutcome.CONNECTED, request.effect_id,
            request.activity_id.value, connector.container_id, instant, instant, 1,
            "11111111-1111-4111-8111-111111111111")
