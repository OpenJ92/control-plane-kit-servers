"""Pure topology input helpers for the #255 real Docker scenario."""
from dataclasses import replace

from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
from control_plane_kit_core.topology.graph import Endpoint, LiteralAddress
from control_plane_kit_core.types import Protocol
from control_plane_kit_servers_cpk_server.client.authoring import (
    GatewayHealthRoutes, GatewayHealthTargetIntent, ReceiverIntroduction, ReceiverScope,
)
from control_plane_kit_core.wrapper_configuration import WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT

from docker_image_update_material import DockerImageMaterial, IMAGES, image_value, selected_metadata


def with_nodes(graph, values):
    """Preserve selected containment order; append only newly introduced nodes."""
    runtime = graph.runtimes["docker"]
    retained = tuple(name for name in runtime.children if name in values)
    added = tuple(name for name in values if name not in graph.nodes)
    return replace(graph, nodes=values, runtimes={"docker":
        replace(runtime, children=retained + added)})


def route_intent(graph):
    targets = [("self", "gateway", "control")]
    targets.extend((name, name, "internal") for name in ("api", "api-y") if name in graph.nodes)
    return GatewayHealthRoutes(ReceiverScope("gateway", "control"), tuple(
        GatewayHealthTargetIntent(alias, ReceiverScope(name, socket), graph.node(name).endpoint(socket).url)
        for alias, name, socket in targets))


class DockerReintroductionMaterial(DockerImageMaterial):
    """One immutable Hello template; CPK authors both receiver incarnations."""
    def __init__(self, workspace_id):
        super().__init__(workspace_id)
        template = self.documents["api-y"].product
        document = ProductDescriptorCodec().encode_document(replace(template,
            image=image_value(IMAGES["hello_family"]["reference"])))
        self.documents["api"] = self.documents["api-y"] = document
        self.product_reference = ProductReference.from_document(document)
        template_node = self.a.node("api-y")
        wrapper, = document.product.runtime_contract.configuration_artifacts
        nodes = dict(self.a.nodes)
        for name in ("api", "api-y"):
            nodes[name] = replace(template_node, node_id=name,
                block_spec=replace(template_node.block_spec, role_id=name),
                endpoints={"internal": Endpoint(LiteralAddress("http://" + name + ":8000"), Protocol.HTTP)},
                configuration_artifacts=(), public_environment=tuple(
                    value for value in document.product.runtime_contract.public_environment
                    if value.name != WORKLOAD_NODE_CONTROL_CONFIGURATION_ENVIRONMENT),
                metadata=selected_metadata(document))
        gateway = nodes["gateway"]
        nodes["gateway"] = replace(gateway, configuration_artifacts=tuple(
            self.routes(("gateway",)) if value.artifact_id == "gateway-health-targets" else value
            for value in gateway.configuration_artifacts))
        self.graph = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(replace(self.a, nodes=nodes,
            runtimes={"docker": replace(self.a.runtimes["docker"],
                children=("gateway", "connector", "api", "api-y"))})))
        self.a = with_nodes(self.graph, {name: self.graph.node(name) for name in ("gateway", "connector")})
        self.introductions = tuple(ReceiverIntroduction(ReceiverScope(name, "internal"),
            wrapper.artifact_id, wrapper.target_path) for name in ("api", "api-y"))
        self.expected_start_roles = {"gateway": "gateway", "connector": "connector",
            "api": "hello_family", "api-y": "hello_family"}
        for name, role in self.expected_start_roles.items():
            assert self.documents[name].product.image.execution_reference == IMAGES[role]["reference"]
