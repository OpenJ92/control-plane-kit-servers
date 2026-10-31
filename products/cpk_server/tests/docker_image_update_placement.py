"""Owned controller membership and provider observations for #251, no scheduler."""
from datetime import datetime, timezone
import json
import os
from types import MappingProxyType

from docker.errors import NotFound

from control_plane_kit_core.configuration_instances import ConfigurationInstanceRefCodec
from control_plane_kit_core.planning import StartRuntime, StartNode, ReconcileNode, resolve_management_observation
from control_plane_kit_core.products import ProductReference
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.runtime_effects import EffectResultKind
from control_plane_kit_core.secrets import SecretFileDelivery
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, validate_graph
from control_plane_kit_core.types import RuntimeKind
from control_plane_kit_interpreters.docker.configuration import (
    configuration_volume_name, require_configuration_owner,
)
from control_plane_kit_interpreters.docker.runtime import (
    _node_labels, _secret_volume_name, _selected_secret_identity,
)
from control_plane_kit_interpreters.docker.sdk import matches_image_reference
from control_plane_kit_operations.runtime_authorities import (
    RegisteredRuntimeAuthorityStatus, LocalDockerSocketAuthority,
)
from control_plane_kit_operations.products import RegisteredProductStatus
from control_plane_kit_operations.effect_outcome_evidence import NativeConnectionObservation, NativeConnectionOutcome
from control_plane_kit_operations.runtime_management_targets import is_native_connection_operation
from control_plane_kit_servers_cpk_server.managed_health_placement import (
    DockerControllerPlacement, DockerGatewayBinding, DockerGatewayEndpointReader,
    DockerRuntimeClientBinding, DockerRuntimeClientSelector,
)

from docker_image_update_material import IMAGES
from docker_image_update_identity import FixedImages
from docker_image_update_ports import FixtureBoundaryFailure


PREFIX = "org.openj92.cpk."


def owned_resources(engine, workspace):
    selector = {"label": PREFIX + "workspace=" + workspace}
    return (engine.containers.list(all=True, filters=selector),
        engine.networks.list(filters=selector), engine.volumes.list(filters=selector))


def dispose_fixture(placement):
    """Exact unique test-world disposal; does not advance or compensate CPK."""
    placement.same_daemon()
    selected = placement.cleanup_candidates()  # Validate the entire set before any disposal.
    containers, networks, volumes = (selected[kind] for kind in ("containers", "networks", "volumes"))
    if placement.network_id is not None and any(value.id == placement.network_id for value in networks):
        placement.detach()
    for container in containers:
        container.remove(force=True)
    for network in networks:
        placement.owned(network.attrs["Labels"], "runtime-network")
        network.reload()
        if network.attrs.get("Containers"):
            raise FixtureBoundaryFailure("owned network has unexplained membership")
        network.remove()
    for volume in volumes:
        volume.remove()
    if any(owned_resources(placement.engine, placement.workspace)):
        raise FixtureBoundaryFailure("owned Docker fixture residue remains")
    print(json.dumps({"docker_image_fixture_disposal": "absent",
        "containers": len(containers), "networks": len(networks),
        "historical_configuration_volumes": sum(value.name in placement.record["volumes"] for value in volumes),
        "secret_volumes": sum(value.name in placement.record["secret_volumes"] for value in volumes)}), flush=True)


class OwnedControllerPlacement:
    def __init__(self, engine, sdk, workspace, controller_id, daemon_id, *, record_path=None, run=None,
                 expected_start_roles=None, qualified_images=None):
        self.engine, self.sdk, self.workspace = engine, sdk, workspace
        self.controller_id, self.daemon_id = controller_id, daemon_id
        if type(qualified_images) is not FixedImages or qualified_images.daemon_id != daemon_id:
            raise FixtureBoundaryFailure("qualified artifact map missing or conflicting")
        self._qualified_images = qualified_images
        if self.engine.info().get("ID") != daemon_id:
            raise FixtureBoundaryFailure("fixture daemon identity changed")
        self.network_id = None
        self.nodes, self.bindings = {}, {}
        self.attachment_attempted = False
        self.failure = None
        roles = dict(expected_start_roles or {})
        if (set(roles) - {"gateway", "api", "api-y", "connector"}
                or any(type(role) is not str or role not in IMAGES for role in roles.values())):
            raise FixtureBoundaryFailure("unknown expected start image role")
        self.expected_start_roles = MappingProxyType(roles)
        self.record_path = record_path
        self.record = {"workspace": workspace, "controller_id": controller_id,
            "daemon_id": daemon_id, "run": run, "intents": [], "containers": {},
            "networks": {}, "volumes": {}, "secret_volumes": {}, "attachment": None,
            "qualified_images": qualified_images.descriptor()}
        self.persist()
        self.provider = DockerRuntimeClientBinding(workspace, "docker", RuntimeAuthorityReference("local-docker"), sdk)
        self.provider_clients = DockerRuntimeClientSelector((self.provider,))
        self.reader = DockerGatewayEndpointReader((DockerControllerPlacement(self.provider, controller_id),), self.binding_for)

    def persist(self):
        if self.record_path is None:
            return
        encoded = json.dumps(self.record, sort_keys=True).encode("utf-8")
        if len(encoded) > 262144:
            raise FixtureBoundaryFailure("fixture resource record exceeded bound")
        temporary = self.record_path.with_suffix(".pending")
        with temporary.open("wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.record_path)

    def require_healthy(self):
        if self.failure is not None:
            raise FixtureBoundaryFailure("resource observation failed; preserve fixture")

    def starting(self, request):
        self.require_healthy()
        self.same_daemon()
        if (request.source.workspace_id != self.workspace
                or request.authority_ref != RuntimeAuthorityReference("local-docker")
                or request.runtime_kind is not RuntimeKind.DOCKER
                or any(value.runtime_id != "docker" for value in request.products)
                or (type(request.operation) is StartRuntime and request.operation.target.runtime_id != "docker")):
            raise FixtureBoundaryFailure("runtime request ownership differs")
        if type(request.operation) is StartNode:
            node = request.operation.target.node_id
            role = self.expected_start_roles.get(node)
            if role is not None:
                selected = [value for value in request.products if value.node_id == node
                    and value.runtime_id == "docker"]
                if (len(selected) != 1
                        or selected[0].product.image.execution_reference != IMAGES[role]["reference"]):
                    raise FixtureBoundaryFailure("selected product differs from expected start image")
        self.record["intents"].append({"effect_id": request.effect_id,
            "activity_id": request.activity_id.value, "run_id": request.source.run_id.value,
            "operation": type(request.operation).__name__})
        if request.configuration_instances is not None:
            for reference in request.configuration_instances.instances:
                if (reference.workspace_id != self.workspace or reference.runtime_id != "docker"
                        or reference.node_id not in {"gateway", "api", "api-y", "connector"}):
                    raise FixtureBoundaryFailure("configuration request scope differs")
                name = configuration_volume_name(reference)
                encoded = ConfigurationInstanceRefCodec().encode(reference)
                if name in self.record["volumes"] and self.record["volumes"][name] != encoded:
                    raise FixtureBoundaryFailure("configuration identity changed")
                self.record["volumes"][name] = encoded
        if type(request.operation) in (StartNode, ReconcileNode):
            for material in request.products:
                if material.node_id != request.operation.target.node_id:
                    continue
                if material.node_id not in {"gateway", "api", "api-y", "connector"}:
                    raise FixtureBoundaryFailure("secret request node scope differs")
                for delivery in material.product.runtime_contract.secret_deliveries:
                    if type(delivery) is not SecretFileDelivery:
                        continue
                    image = self.sdk.inspect_image(material.product.image.execution_reference)
                    if image is None or not matches_image_reference(
                            material.product.image.execution_reference, image.repo_digests):
                        raise FixtureBoundaryFailure("secret recipient image is not admitted")
                    owner_uid = image.secret_file_owner_uid()
                    selection, = (value for value in material.secret_selections
                        if value.reference == delivery.reference and value.intent is delivery.intent)
                    name = _secret_volume_name(request, material.node_id, delivery, owner_uid=owner_uid)
                    labels = {**_node_labels(request, material), PREFIX + "volume.kind": "secret-file",
                        PREFIX + "secret.target": delivery.target_path,
                        PREFIX + "secret.reference": delivery.reference.reference_id,
                        PREFIX + "secret.identity": _selected_secret_identity(
                            request, material.node_id, delivery, selection, owner_uid)}
                    prior = self.record["secret_volumes"].get(name)
                    stable = ("workspace", "runtime", "node", "kind", "volume.kind",
                        "secret.target", "secret.reference", "secret.identity")
                    if (name in self.record["volumes"] or prior is not None
                            and any(prior.get(PREFIX + key) != labels.get(PREFIX + key) for key in stable)):
                        raise FixtureBoundaryFailure("secret volume identity changed")
                    # Reuse retains the first allocation's ownership labels;
                    # plan/image coordinates are not selected file identity.
                    if prior is None:
                        self.record["secret_volumes"][name] = labels
        self.persist()  # Exact owner-derived allocation identities are durable before dispatch.

    def observed(self, record):
        self.same_daemon()
        request, result = record.request, record.result
        if result.kind is not EffectResultKind.SUCCEEDED:
            return  # Unrecorded partial effects are discovered and preserved by disposal.
        operation = request.operation
        if type(operation) is StartRuntime:
            network = self.engine.networks.get(result.evidence["network"])
            self.owned(network.attrs["Labels"], "runtime-network")
            observed = self.sdk.inspect_network(network.id)
            if observed is None or observed.network_id != network.id:
                raise FixtureBoundaryFailure("returned network has no verified identity")
            self.record["networks"][network.id] = "docker"
        elif type(operation) in (StartNode, ReconcileNode):
            node = operation.target.node_id
            product, = [value.product for value in request.products if value.node_id == node
                and value.runtime_id == "docker"]
            role, = [key for key, value in IMAGES.items()
                if value["reference"] == product.image.execution_reference]
            container = self.engine.containers.get(result.evidence["container"])
            self.owned(container.labels, "container", node)
            self.nodes[node] = container.id
            self.inspect_node(node, image_role=role)
            self.record["containers"][container.id] = {"node": node, "image_role": role}
        self.persist()

    def cleanup_candidates(self):
        """Discovery diagnoses; only independently recorded IDs/ref values authorize."""
        self.require_healthy()
        self.same_daemon()
        managers = {"containers": self.engine.containers, "networks": self.engine.networks,
            "volumes": self.engine.volumes}
        found = {}
        for kind, manager in managers.items():
            recorded = self.record[kind]
            if kind == "volumes":
                if recorded.keys() & self.record["secret_volumes"].keys():
                    raise FixtureBoundaryFailure("fixture volume ownership classes overlap")
                recorded = {**recorded, **self.record["secret_volumes"]}
            candidates = manager.list(**({"all": True} if kind == "containers" else {}),
                filters={"label": PREFIX + "workspace=" + self.workspace})
            identities = {value.name if kind == "volumes" else value.id for value in candidates}
            if not identities <= recorded.keys():
                raise FixtureBoundaryFailure("unrecorded workspace resource; preserve fixture")
            found[kind] = []
            for identity, expected in recorded.items():
                try:
                    value = manager.get(identity)
                except NotFound:
                    continue
                if (value.name if kind == "volumes" else value.id) != identity:
                    raise FixtureBoundaryFailure("recorded resource identity differs")
                if kind == "containers":
                    self.owned(value.labels, "container", expected["node"])
                    if value.attrs["Image"] != self.expected_image_id(expected["image_role"]):
                        raise FixtureBoundaryFailure("recorded container image differs")
                elif kind == "networks":
                    self.owned(value.attrs["Labels"], "runtime-network")
                    members = set(value.attrs.get("Containers", {}))
                    allowed = set(self.record["containers"])
                    if self.record["attachment"] == {"network_id": identity,
                            "controller_id": self.controller_id}:
                        allowed.add(self.controller_id)
                    if not members <= allowed:
                        raise FixtureBoundaryFailure("recorded network has unexplained membership")
                elif identity in self.record["secret_volumes"]:
                    observed = self.sdk.inspect_volume(identity)
                    if (observed is None or observed.name != identity
                            or any(value.attrs["Labels"].get(key) != item for key, item in expected.items())
                            or any(observed.labels.get(key) != item for key, item in expected.items())):
                        raise FixtureBoundaryFailure("recorded secret volume ownership differs")
                else:
                    reference = ConfigurationInstanceRefCodec().decode(expected)
                    if configuration_volume_name(reference) != identity:
                        raise FixtureBoundaryFailure("recorded configuration identity differs")
                    require_configuration_owner(self.sdk.inspect_volume(identity), reference)
                found[kind].append(value)
        return found

    def same_daemon(self):
        if self.engine.info().get("ID") != self.daemon_id:
            raise FixtureBoundaryFailure("fixture daemon identity changed")
        if (self._qualified_images.daemon_id != self.daemon_id
                or self.record.get("daemon_id") != self.daemon_id
                or self.record.get("qualified_images") != self._qualified_images.descriptor()):
            raise FixtureBoundaryFailure("qualified artifact map changed; preserve fixture")

    def expected_image_id(self, role):
        if role not in self._qualified_images.images:
            raise FixtureBoundaryFailure("qualified artifact role missing")
        return self._qualified_images.images[role].execution_id

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
            self.record["attachment"] = {"network_id": network.id, "controller_id": self.controller_id}
            self.persist()
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
        role = image_role or self.expected_start_roles.get(name) or (
            name if name in {"gateway", "connector"} else "hello_a")
        if (observed is None or observed.container_id != container.id or not observed.running
                or container.attrs["Image"] != self.expected_image_id(role)
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
    def __init__(self, placement, ingress, material):
        self.placement, self.ingress, self.material = placement, ingress, material
        self.provider_clients = placement.provider_clients
        self.reads = []

    def select(self, *, plan, current, desired, registered_products, runtime_authorities):
        authorities = [value for value in runtime_authorities if value.workspace_id == self.placement.workspace
            and value.authority_ref == RuntimeAuthorityReference("local-docker")
            and value.runtime_kind is RuntimeKind.DOCKER
            and value.status is RegisteredRuntimeAuthorityStatus.ACTIVE
            and type(value.authority) is LocalDockerSocketAuthority]
        if len(authorities) != 1:
            return None
        current, desired = validate_graph(current), validate_graph(desired)
        required = []
        for activity in plan.activities:
            if not is_native_connection_operation(activity.operation):
                continue
            resolved = resolve_management_observation(activity.operation, current, desired,
                expected_operation=plan.activity(activity.activity_id).operation)
            graph = resolved.selected_graph.graph
            runtime = graph.runtimes[activity.operation.target.runtime_id]
            if (runtime.runtime_id != "docker" or runtime.kind is not RuntimeKind.DOCKER
                    or runtime.authority_ref != authorities[0].authority_ref
                    or resolved.ingress != self.material.a.public_ingresses[0]
                    or resolved.gateway_node.node_id != "gateway"
                    or resolved.connector_node.node_id != "connector"
                    or resolved.gateway_readiness_socket != "control"
                    or any(node.runtime_id != "docker" or node.metadata != self.material.a.node(name).metadata
                        for node, name in ((resolved.gateway_node, "gateway"),
                            (resolved.connector_node, "connector")))):
                return None
            for name in ("gateway", "connector"):
                expected = self.material.documents[name]
                products = [value for value in registered_products
                    if value.workspace_id == self.placement.workspace
                    and value.reference == ProductReference.from_document(expected)
                    and value.status is RegisteredProductStatus.ACTIVE]
                if len(products) != 1 or products[0].descriptor_document != expected:
                    return None
            required.append(activity.activity_id)
        return tuple(required)

    async def observe_connection(self, realization, request, authority):
        current = DEFAULT_GRAPH_CODEC.decode(realization.base_graph.graph_descriptor)
        desired = DEFAULT_GRAPH_CODEC.decode(realization.desired_graph.graph_descriptor)
        selected = self.select(plan=realization.plan,
            current=current, desired=desired,
            registered_products=realization.registered_products,
            runtime_authorities=realization.runtime_authorities)
        if (selected is None or request.activity_id not in selected or len(self.ingress.allocations) != 1
                or authority.authority_ref != request.authority_ref
                or authority.workspace_id != self.placement.workspace
                or authority not in realization.runtime_authorities
                or request.source.workspace_id != self.placement.workspace):
            raise FixtureBoundaryFailure("synthetic native scope differs")
        resolve_management_observation(request.operation, validate_graph(current), validate_graph(desired),
            expected_operation=realization.plan.activity(request.activity_id).operation)
        allocation, = self.ingress.allocations.values()
        if allocation.hostname != self.material.a.public_ingresses[0].hostname:
            raise FixtureBoundaryFailure("synthetic allocation target differs")
        connector = self.placement.inspect_node("connector")
        instant = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.reads.append((request.effect_id, request.activity_id.value, connector.container_id))
        return NativeConnectionObservation(NativeConnectionOutcome.CONNECTED, request.effect_id,
            request.activity_id.value, connector.container_id, instant, instant, 1,
            "11111111-1111-4111-8111-111111111111")
