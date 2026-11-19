"""Pure authored inputs for the real same-image Hello cutover.

An image reference here is data, not qualification. The live caller must supply
the actually approved/pulled Hello artifact; no future coordinate is embedded.
"""
from dataclasses import replace

import control_plane_kit_core as core
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_servers_cpk_server.client.authoring import (
    GatewayHealthRoutes, GatewayHealthTargetIntent, ReceiverScope,
)
from control_plane_kit_servers_hello_server.configuration import hello_control_configuration_artifact

from docker_image_update_material import image_value, selected_metadata


def declaration_documents(material, hello_reference):
    """Two registered defaults differ only in the supported health declaration."""
    if not hello_reference.startswith("ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:"):
        raise ValueError("declaration witness requires an exact Hello repository digest")
    original = material.successor.product
    both = replace(original, identity=replace(original.identity,
        contract_revision=original.identity.contract_revision + 1), image=image_value(hello_reference))
    codec = core.ReceiverNodeControlConfigurationCodec()
    wrapper, = [value for value in both.runtime_contract.configuration_artifacts
        if value.artifact_id == "hello-control"]
    configuration = codec.decode_bytes(wrapper.content.encode("utf-8"))
    assert configuration.declaration.surface.health_reads == (
        core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)
    declaration = replace(configuration.declaration, surface=replace(configuration.declaration.surface,
        health_reads=(core.NodeHealthReadKind.READINESS,)))
    selected = hello_control_configuration_artifact(replace(configuration, declaration=declaration))
    readiness = replace(both, identity=replace(both.identity, contract_revision=both.identity.contract_revision + 1),
        runtime_contract=replace(both.runtime_contract, control_surfaces=(declaration.surface,),
            configuration_artifacts=tuple(selected if value.artifact_id == wrapper.artifact_id else value
                for value in both.runtime_contract.configuration_artifacts)))
    encoder = ProductDescriptorCodec()
    return encoder.encode_document(both), encoder.encode_document(readiness)


def declaration_graph(graph, document):
    """Explicit desired surface/product; selected wrapper authoring stays in CPK."""
    node = graph.node("api")
    return graph.update_node(replace(node,
        block_spec=replace(node.block_spec, control_surfaces=document.product.runtime_contract.control_surfaces),
        metadata=selected_metadata(document)))


def current_route_intent(graph):
    """Preserve every selected alias/origin and scope as explicit route intent."""
    artifact, = [value for value in graph.node("gateway").configuration_artifacts
        if value.artifact_id == "gateway-health-targets"]
    routes = core.ReceiverManagementRoutesCodec().decode_bytes(artifact.content.encode("utf-8"))
    return GatewayHealthRoutes(ReceiverScope("gateway", "control"), tuple(
        GatewayHealthTargetIntent(binding.target_id,
            ReceiverScope(binding.target.node_id.value, binding.target.provider_socket_name.value), binding.origin)
        for binding in routes.targets))
