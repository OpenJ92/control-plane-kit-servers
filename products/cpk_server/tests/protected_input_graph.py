"""Pure source-witness graph from authenticated context and generated public keys."""
from dataclasses import replace

import control_plane_kit_core as core
from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime
from control_plane_kit_core.products import (
    ContainerServerProduct, OciImageReference, ProductCatalog, ProductDescriptorCodec,
    ProductIdentity, ProductInstanceConfiguration, instantiate_catalog_product,
)
from control_plane_kit_core.public_ingress import IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.topology import compile_topology, validate_graph
from control_plane_kit_servers_cloudflared_connector import managed
from control_plane_kit_servers_cpk_local_gateway import health_relay_configuration as relay
from control_plane_kit_servers_cpk_local_gateway.control_configuration import (
    gateway_control_configuration_artifact, gateway_control_declaration,
)
from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import (
    GatewayHealthTransitConfiguration, gateway_health_transit_configuration_artifact,
)
from control_plane_kit_servers_cpk_server.client.authoring import ReceiverScope, prepare_receiver_configuration
from control_plane_kit_servers_hello_server.configuration import (
    hello_control_configuration_artifact, hello_control_declaration, hello_source_runtime_contract,
)
from protected_input_provider import WORKSPACE


def source_document(name, contract):
    # Explicit source witness coordinates; no association with a published image.
    return ProductDescriptorCodec().encode_document(ContainerServerProduct(
        ProductIdentity("protected-input-witness", name, 1),
        OciImageReference("example.invalid", "never-executed/" + name, "sha256:" + "a" * 64), contract))


def declared_documents():
    return {"gateway": source_document("gateway", relay.gateway_health_declared_runtime_contract()),
            "connector": source_document("connector", managed.declared_runtime_contract())}


def authored_graph(documents, context, verifiers, transit_public):
    """Use existing product/receiver owners; never construct managed key material."""
    configurations = {}
    for name, socket, identity, declaration in (
        ("hello", "internal", "a", hello_control_declaration()),
        ("gateway", "control", "b", gateway_control_declaration()),
        ("connector", "control", "c", managed.control_declaration()),
    ):
        configurations[name] = prepare_receiver_configuration(workspace_id=WORKSPACE,
            runtime_id="docker", scope=ReceiverScope(name, socket), receiver_id=identity * 32,
            declaration=declaration, context=context,
            verifier_configuration={"workload_verifier_configuration": verifiers["workload_verifier_configuration"]})
    hello_artifact = hello_control_configuration_artifact(configurations["hello"])
    documents = {**documents, "hello": source_document("hello", hello_source_runtime_contract(hello_artifact))}
    routes = relay.gateway_health_relay_configuration_artifact(core.ReceiverManagementRoutes(
        configurations["gateway"].target, tuple(relay.gateway_health_target_binding(
            target_id="self" if name == "gateway" else name,
            target=configurations[name].target, runtime_contract=documents[name].product.runtime_contract,
            hostname=name) for name in ("gateway", "hello", "connector"))))
    key = core.DelegationPublicKey(transit_public["key_id"],
        core.DelegationKeyAlgorithm(transit_public["algorithm"]), transit_public["public_key_pem"])
    trust = gateway_health_transit_configuration_artifact(GatewayHealthTransitConfiguration(
        configurations["gateway"].target, "cpk-server",
        core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, (key,)))
    artifacts = {"hello": (hello_artifact,),
        "gateway": (trust, routes, gateway_control_configuration_artifact(configurations["gateway"])),
        "connector": (managed.control_configuration_artifact(configurations["connector"]),)}
    catalogue = ProductCatalog.from_documents(tuple(documents.values()))
    blocks = tuple(instantiate_catalog_product(catalogue, document.product.identity, role_id=name,
        configuration=ProductInstanceConfiguration(public_environment=document.product.runtime_contract.public_environment,
            configuration_artifacts=artifacts[name], secret_deliveries=())) for name, document in documents.items())
    graph = compile_topology(DeploymentTopology("protected-input-preparation",
        DockerRuntime(runtime_id="docker", children=blocks)))
    graph = replace(graph, runtimes={"docker": replace(graph.runtimes["docker"],
        authority_ref=RuntimeAuthorityReference("local-docker"), management=core.RuntimeManagement("gateway", "management"))},
        public_ingresses=(NamedPublicIngress("management", IngressAuthorityReference("zone"),
            PublicIngressTarget("gateway", "control"), "connector", "cpk-input.example.invalid"),))
    validate_graph(graph).require_valid()
    # Startup's gateway document remains instance-free and keeps its exact identity/digest.
    for name in ("gateway", "connector"):
        assert not documents[name].product.runtime_contract.configuration_artifacts
        assert graph.node(name).metadata["product_descriptor_digest"] == documents[name].content_digest
        assert graph.node(name).metadata["product_identity"] == documents[name].product.identity.key
    return graph, documents, configurations
