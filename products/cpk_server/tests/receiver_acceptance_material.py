"""Issue 1912 authored inputs; ephemeral keys, never completed Operations truth."""
from dataclasses import replace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, BlockSpec, ProviderSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import (
    ContainerServerProduct, OciImageReference, ProductDescriptorCodec, ProductIdentity,
    ProductReference, ProductRuntimeContract, ProviderRuntimePort,
)
from control_plane_kit_core.public_ingress import (
    IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget,
)
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.topology import DeploymentGraph, Node, RuntimeRecord, validate_graph
from control_plane_kit_core.topology.graph import Endpoint, LiteralAddress
from control_plane_kit_core.types import BlockFamily, Protocol, RuntimeKind
from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration
from control_plane_kit_servers_cpk_local_gateway.control_configuration import (
    gateway_control_configuration_artifact, gateway_control_declaration,
)
from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import (
    gateway_health_relay_configuration_artifact, gateway_health_source_runtime_contract,
)
from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import (
    GatewayHealthTransitConfiguration, gateway_health_transit_configuration_artifact,
)
from control_plane_kit_servers_cpk_server.health_receiver_adapters import health_receiver_decoders


class AuthoredMaterial:
    """One original X receiver and G; B adds Y, C restores A's selected bytes."""

    def __init__(self):
        self.private, self.public = {}, {}
        for family in ("transit", "workload"):
            private = Ed25519PrivateKey.generate()
            self.private[family] = private.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            self.public[family] = core.DelegationPublicKey("health-" + family,
                core.DelegationKeyAlgorithm.ED25519,
                private.public_key().public_bytes(serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii"))
        self.documents = {}
        self.configurations = {name: self.configuration(name) for name in ("gateway", "api", "api-y")}
        trust = gateway_health_transit_configuration_artifact(GatewayHealthTransitConfiguration(
            self.configurations["gateway"].target, "cpk-server",
            core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, (self.public["transit"],)))
        gateway_contract = gateway_health_source_runtime_contract(trust,
            self.routes(("gateway", "api")),
            gateway_control_configuration_artifact(self.configurations["gateway"]))
        wrapper = self.wrapper("api")
        surface = self.configurations["api"].declaration.surface
        workload_contract = ProductRuntimeContract(
            sockets=BlockSockets(providers=(ProviderSocket("http", Protocol.HTTP),)),
            provider_ports=(ProviderRuntimePort("http", 8000),),
            capabilities=(CapabilityName.NODE_CONTROLLABLE, CapabilityName.HEALTH_CHECKABLE),
            control_surfaces=(surface,), configuration_artifacts=(wrapper,),
            public_environment=(PublicStaticEnvironmentBinding("CPK_WRAPPER_CONFIGURATION_FILE", wrapper.target_path),))
        connector_contract = ProductRuntimeContract(sockets=BlockSockets())
        nodes = {name: self.node(name, contract) for name, contract in (
            ("gateway", gateway_contract), ("api", workload_contract), ("connector", connector_contract))}
        self.a = DeploymentGraph("receiver-acceptance", nodes=nodes,
            runtimes={"docker": RuntimeRecord("docker", RuntimeKind.DOCKER,
                tuple(nodes), authority_ref=RuntimeAuthorityReference("local-docker"),
                management=core.RuntimeManagement("gateway", "management"))},
            public_ingresses=(NamedPublicIngress("management", IngressAuthorityReference("zone"),
                PublicIngressTarget("gateway", "control"), "connector", "cpk-1912.example.invalid"),))
        y = replace(nodes["api"], node_id="api-y",
            block_spec=replace(nodes["api"].block_spec, role_id="api-y"),
            endpoints={"http": Endpoint(LiteralAddress("http://api-y:8000"), Protocol.HTTP)},
            configuration_artifacts=(self.wrapper("api-y"),))
        gateway_b = replace(nodes["gateway"], configuration_artifacts=tuple(
            self.routes(("gateway", "api", "api-y")) if artifact.artifact_id == "gateway-health-targets"
            else artifact for artifact in nodes["gateway"].configuration_artifacts))
        self.b = replace(self.a, nodes={**nodes, "gateway": gateway_b, "api-y": y},
            runtimes={"docker": replace(self.a.runtimes["docker"], children=(*nodes, "api-y"))})
        self.c = self.a
        for graph in (self.a, self.b, self.c):
            validate_graph(graph).require_valid()
        self.decoders = health_receiver_decoders(gateway_documents=(self.documents["gateway"],))

    def configuration(self, name):
        roles = core.NodeControlGraphReferenceRole
        socket = "control" if name == "gateway" else "http"
        target = core.NodeControlReceiverTarget(
            core.NodeControlGraphReference(roles.WORKSPACE, "workspace-a"),
            core.NodeControlGraphReference(roles.RUNTIME, "docker"),
            core.NodeControlGraphReference(roles.NODE, name),
            core.NodeControlGraphReference(roles.PROVIDER_SOCKET, socket),
            {"gateway": "b", "api": "a", "api-y": "c"}[name] * 32)
        declaration = (gateway_control_declaration() if name == "gateway" else
            core.WorkloadNodeControlSurfaceDeclaration(core.WorkloadNodeControlSurfaceDescriptor(
                target.provider_socket_name, (), (core.NodeHealthReadKind.READINESS,)),
                core.WorkloadNodeControlSurfaceDeclarationProfile.V2))
        verifiers = tuple(NodeControlVerificationConfiguration(purpose, "cpk-server", (self.public["workload"],))
            for purpose in (core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
                core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ))
        return core.ReceiverNodeControlConfiguration(target, declaration, verifiers)

    def wrapper(self, name):
        return ConfigurationArtifact("workload-control", "/etc/cpk/workload/control.json",
            ConfigurationMediaType.JSON,
            core.ReceiverNodeControlConfigurationCodec().encode_bytes(self.configurations[name]).decode())

    def routes(self, names):
        gateway = self.configurations["gateway"]
        return gateway_health_relay_configuration_artifact(core.ReceiverManagementRoutes(gateway.target,
            tuple(core.ReceiverManagementRouteBinding("self" if name == "gateway" else name,
                self.configurations[name].target, self.configurations[name].declaration,
                "http://" + name + ":8000") for name in names)))

    def node(self, name, contract):
        document = ProductDescriptorCodec().encode_document(ContainerServerProduct(
            ProductIdentity("receiver-test", name, 1),
            OciImageReference("example.invalid", "never-executed/" + name, "sha256:" + "a" * 64), contract))
        self.documents[name] = document
        reference = ProductReference.from_document(document)
        return Node(name, BlockFamily.APPLICATION,
            BlockSpec(name, capabilities=contract.capabilities, control_surfaces=contract.control_surfaces,
                gateway_transit=contract.gateway_transit), "container-server", "docker", contract.sockets,
            endpoints={socket.name: Endpoint(LiteralAddress("http://" + name + ":8000"), socket.protocol)
                for socket in contract.sockets.providers},
            public_environment=contract.public_environment, configuration_artifacts=contract.configuration_artifacts,
            metadata={"product_identity": reference.identity.key,
                "product_descriptor_digest": reference.descriptor_sha256.value})
