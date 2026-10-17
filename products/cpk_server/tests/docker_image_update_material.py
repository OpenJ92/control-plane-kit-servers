"""Authored #251 values; qualified images, one immutable receiver configuration."""
from dataclasses import replace
import json
from pathlib import Path

import control_plane_kit_core as core
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from control_plane_kit_core.algebra import BlockSockets, BlockSpec
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.secrets import SecretEnvironmentDelivery, SecretReference, SecretUseIntent
from control_plane_kit_core.secret_selections import author_secret_selections
from control_plane_kit_core.products import (
    ContainerServerProduct, OciImageReference, ProductDescriptorCodec, ProductIdentity, ProductReference,
    ProductRuntimeContract,
)
from control_plane_kit_core.public_ingress import IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph, Node, RuntimeRecord, validate_graph
from control_plane_kit_core.topology.graph import Endpoint, LiteralAddress
from control_plane_kit_core.types import BlockFamily, Protocol, RuntimeKind
from control_plane_kit_servers_cpk_local_gateway.control_configuration import gateway_control_configuration_artifact
from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import gateway_health_source_runtime_contract
from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import (
    GatewayHealthTransitConfiguration, gateway_health_transit_configuration_artifact,
)
from control_plane_kit_servers_cpk_server.health_receiver_adapters import health_receiver_decoders
from control_plane_kit_servers_hello_server.configuration import (
    hello_control_configuration_artifact, hello_control_declaration, hello_source_runtime_contract,
)

from receiver_acceptance_material import AuthoredMaterial


IMAGES = json.loads(Path(__file__).with_name("docker_image_update_images.json").read_text())
APPLICATION_REFERENCE = SecretReference("secret://application-secrets/api/token")
APPLICATION_INTENT = SecretUseIntent.APPLICATION_CONTROL_TOKEN


def image_value(reference):
    repository, digest = reference.split("@", 1)
    registry, path = repository.split("/", 1)
    return OciImageReference(registry, path, digest)


def selected_metadata(document):
    reference = ProductReference.from_document(document)
    return {"product_identity": reference.identity.key,
        "product_descriptor_digest": reference.descriptor_sha256.value,
        "oci_image": document.product.image.execution_reference}


class DockerImageMaterial(AuthoredMaterial):
    """Reuse authored key/graph constructors, not the earlier compute substitutes."""
    def __init__(self, workspace_id):
        self.workspace_id = workspace_id
        self.private, self.public, self.documents = {}, {}, {}
        for family in ("transit", "workload", "workload-overlap"):
            key = Ed25519PrivateKey.generate()
            self.private[family] = key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            self.public[family] = core.DelegationPublicKey("health-" + family,
                core.DelegationKeyAlgorithm.ED25519, key.public_key().public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii"))
        self.configurations = {name: self.configuration(name) for name in ("gateway", "api", "api-y")}
        trust = gateway_health_transit_configuration_artifact(GatewayHealthTransitConfiguration(
            self.configurations["gateway"].target, "cpk-server",
            core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, (self.public["transit"],)))
        gateway = gateway_health_source_runtime_contract(trust, self.routes(("gateway", "api", "api-y")),
            gateway_control_configuration_artifact(self.configurations["gateway"]))
        api = hello_source_runtime_contract(self.wrapper("api"))
        api = replace(api, secret_deliveries=(SecretEnvironmentDelivery("CPK_WITNESS_TOKEN",
            APPLICATION_REFERENCE, APPLICATION_INTENT),), configuration_artifacts=(
                *api.configuration_artifacts, ConfigurationArtifact("application-settings",
                    "/etc/cpk/application-settings.json", ConfigurationMediaType.JSON, '{"revision":1}')))
        nodes = {name: self.node(name, contract) for name, contract in (
            ("gateway", gateway), ("api", api),
            ("api-y", hello_source_runtime_contract(self.wrapper("api-y"))),
            ("connector", ProductRuntimeContract(sockets=BlockSockets())))}
        self.a = DeploymentGraph("docker-image-update", nodes=nodes,
            runtimes={"docker": RuntimeRecord("docker", RuntimeKind.DOCKER, tuple(nodes),
                authority_ref=RuntimeAuthorityReference("local-docker"),
                management=core.RuntimeManagement("gateway", "management"))},
            public_ingresses=(NamedPublicIngress("management", IngressAuthorityReference("zone"),
                PublicIngressTarget("gateway", "control"), "connector", "cpk-1912.example.invalid"),))
        self.a = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(self.a))
        self.decoders = health_receiver_decoders(gateway_documents=(self.documents["gateway"],))
        original = self.documents["api"]
        self.successor = ProductDescriptorCodec().encode_document(replace(original.product,
            identity=replace(original.product.identity, contract_revision=2),
            image=image_value(IMAGES["hello_b"]["reference"])))
        assert original.product.runtime_contract == self.successor.product.runtime_contract
        validate_graph(self.a).require_valid()

    def configuration(self, name):
        configuration = super().configuration(name)
        target = replace(configuration.target,
            workspace_id=core.NodeControlGraphReference(
                core.NodeControlGraphReferenceRole.WORKSPACE, self.workspace_id))
        if name != "gateway":
            target = replace(target, provider_socket_name=core.NodeControlGraphReference(
                core.NodeControlGraphReferenceRole.PROVIDER_SOCKET, "internal"))
        return replace(configuration, target=target,
            declaration=configuration.declaration if name == "gateway" else hello_control_declaration())

    def wrapper(self, name):
        return hello_control_configuration_artifact(self.configurations[name])

    def node(self, name, contract):
        role = name if name in {"gateway", "connector"} else "hello_a"
        document = ProductDescriptorCodec().encode_document(ContainerServerProduct(
            ProductIdentity("docker-image-witness", name, 1),
            image_value(IMAGES[role]["reference"]), contract))
        self.documents[name] = document
        return Node(name, BlockFamily.APPLICATION,
            BlockSpec(name, capabilities=contract.capabilities, control_surfaces=contract.control_surfaces,
                gateway_transit=contract.gateway_transit, verification=contract.verification),
            "container-server", "docker", contract.sockets,
            endpoints={socket.name: Endpoint(LiteralAddress("http://" + name + ":8000"), Protocol.HTTP)
                for socket in contract.sockets.providers},
            public_environment=contract.public_environment, configuration_artifacts=contract.configuration_artifacts,
            secret_deliveries=contract.secret_deliveries,
            secret_selections=author_secret_selections(contract.secret_deliveries),
            metadata=selected_metadata(document))
