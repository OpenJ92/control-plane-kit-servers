"""Compiled topology and typed effect inputs, never admitted Operations state."""
from dataclasses import replace
from types import SimpleNamespace

import control_plane_kit_core as core
from control_plane_kit_core.algebra import BlockSockets, ProviderSocket
from control_plane_kit_core.capabilities import CapabilityName
from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationArtifactRequirement, ConfigurationMediaType
from control_plane_kit_core.configuration_instances import ConfigurationInstanceRef, ConfigurationInstanceSelection
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.operations import RunId
from control_plane_kit_core.products import ProductReference, ProductRuntimeContract, ProviderRuntimePort
from control_plane_kit_core.runtime_effects import RuntimeEffectKind, RuntimeEffectRequest, RuntimeEffectSource, RuntimeProductMaterial
from control_plane_kit_core.secret_installation import (
    SecretInstallationDisposition, SecretInstallationReceipt,
    secret_installation_correlation_for_request, secret_material_selection_fingerprint,
)
from control_plane_kit_core.secret_selections import SecretVersionSelection
from control_plane_kit_core.secrets import SecretFileDelivery, SecretFilePathBinding, SecretReference, SecretUseIntent
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph, validate_graph
from control_plane_kit_core.types import Protocol, RuntimeKind
from control_plane_kit_operations.connector_installation import CurrentConnectorInstallation
from control_plane_kit_operations.products import InlineDescriptorSource, RegisteredProduct
from control_plane_kit_operations.runtime_authorities import LocalDockerSocketAuthority, RegisteredRuntimeAuthority
from control_plane_kit_operations.runtime_management_targets import is_native_connection_operation
from receiver_acceptance_material import AuthoredMaterial


class NativeMaterial:
    def __init__(self, *, retained=False):
        authored = self.authored = AuthoredMaterial()
        roles = core.NodeControlGraphReferenceRole
        declaration = core.WorkloadNodeControlSurfaceDeclaration(
            core.WorkloadNodeControlSurfaceDescriptor(
                core.NodeControlGraphReference(roles.PROVIDER_SOCKET, "control"), (),
                (core.NodeHealthReadKind.LIVENESS, core.NodeHealthReadKind.READINESS)),
            core.WorkloadNodeControlSurfaceDeclarationProfile.V2)
        receiver = replace(authored.configurations["api"],
            target=core.NodeControlReceiverTarget(*(
                core.NodeControlGraphReference(role, value) for role, value in (
                    (roles.WORKSPACE, "workspace-a"), (roles.RUNTIME, "docker"),
                    (roles.NODE, "connector"), (roles.PROVIDER_SOCKET, "control"))), "d" * 32),
            declaration=declaration)
        authored.configurations["connector"] = receiver
        artifact = self.artifact = ConfigurationArtifact("cloudflared-control", "/etc/cpk/cloudflared/control.json",
            ConfigurationMediaType.JSON, core.ReceiverNodeControlConfigurationCodec().encode_bytes(receiver).decode())
        contract = ProductRuntimeContract(
            sockets=BlockSockets(providers=(ProviderSocket("control", Protocol.HTTP),)),
            provider_ports=(ProviderRuntimePort("control", 8000),),
            capabilities=(CapabilityName.HEALTH_CHECKABLE, CapabilityName.NODE_CONTROLLABLE),
            control_surfaces=(declaration.surface,),
            public_environment=(PublicStaticEnvironmentBinding("CPK_WRAPPER_CONFIGURATION_FILE", artifact.target_path),),
            configuration_requirements=(ConfigurationArtifactRequirement(artifact.artifact_id,
                artifact.target_path, artifact.media_type, artifact.file_mode),))
        delivery = SecretFileDelivery("/run/secrets/tunnel", SecretReference("secret://fixture/tunnel"),
            SecretUseIntent.CLOUDFLARE_TUNNEL_TOKEN, path_binding=SecretFilePathBinding("TUNNEL_TOKEN_FILE"))
        connector = replace(authored.node("connector", contract), configuration_artifacts=(artifact,),
            secret_deliveries=(delivery,))
        self.document = authored.documents["connector"]
        self.reference = ProductReference.from_document(self.document)
        gateway = authored.a.nodes["gateway"]
        gateway = replace(gateway, configuration_artifacts=tuple(
            authored.routes(("gateway", "api", "connector")) if item.artifact_id == "gateway-health-targets"
            else item for item in gateway.configuration_artifacts))
        application = ConfigurationArtifact("application", "/etc/app/settings.json", ConfigurationMediaType.JSON,
            '{"color":"blue"}')
        api = authored.a.nodes["api"]
        api = replace(api, configuration_artifacts=(*api.configuration_artifacts, application))
        installed = replace(authored.a, nodes={"gateway": gateway, "connector": connector, "api": api})
        empty = DeploymentGraph(installed.name)
        fresh = core.compile_graph_activity_plan(validate_graph(empty), validate_graph(installed))
        assert fresh.ready_for_execution, "fresh native fixture must compile"
        self.current, self.desired = empty, installed
        if retained:
            self.current = installed
            self.desired = installed.update_node(replace(api, configuration_artifacts=(
                *api.configuration_artifacts[:-1], replace(application, content='{"color":"green"}', source_digest=None))))
        pair = validate_graph(self.current), validate_graph(self.desired)
        for graph in pair:
            graph.require_valid()
        self.plan = (core.compile_managed_update_activity_plan(*pair) if retained
            else core.compile_graph_activity_plan(*pair))
        assert self.plan.ready_for_execution, "native fixture must compile"
        activity, = (item for item in self.plan.activities if is_native_connection_operation(item.operation))
        self.authority = RegisteredRuntimeAuthority("registration", "workspace-a",
            installed.runtimes["docker"].authority_ref, RuntimeKind.DOCKER,
            LocalDockerSocketAuthority(), "operator", "2026-10-20T00:00:00Z")
        self.products = tuple(RegisteredProduct("product-" + name, "workspace-a",
            ProductReference.from_document(document), document, InlineDescriptorSource(),
            "operator", "2026-10-20T00:00:00Z") for name, document in authored.documents.items())
        material = RuntimeProductMaterial("connector", "docker", self.reference,
            replace(self.document.product, runtime_contract=replace(contract, configuration_requirements=(),
                configuration_artifacts=(artifact,), secret_deliveries=(delivery,))),
            public_environment=contract.public_environment,
            secret_selections=(SecretVersionSelection(delivery.reference, delivery.intent, "fixture-version"),))
        self.request = RuntimeEffectRequest("native-effect", RuntimeEffectKind.REALIZE_ACTIVITY, RuntimeKind.DOCKER,
            RuntimeEffectSource("workspace-a", "request", RunId("run"), "plan", "base", "desired", "native-effect"),
            activity.activity_id, activity.operation, self.authority.authority_ref, products=(material,))
        installation = None
        if retained:
            start, = (item for item in fresh.activities if type(item.operation) is core.StartNode
                and item.operation.target.node_id == "connector")
            allocation = ConfigurationInstanceRef("allocation", "workspace-a", "docker", "connector",
                artifact.artifact_id, artifact.target_path, artifact.media_type, artifact.file_mode, artifact.content_digest)
            original = replace(self.request, effect_id="installation-effect",
                kind=RuntimeEffectKind.CONFIGURATION_ACTIVITY_V1,
                source=replace(self.request.source, intent_event_id="installation-effect", plan_id="installation-plan"),
                activity_id=start.activity_id, operation=start.operation,
                configuration_instances=ConfigurationInstanceSelection((allocation,)))
            receipt = SecretInstallationReceipt(secret_installation_correlation_for_request(original).request_fingerprint,
                secret_material_selection_fingerprint(original), SecretInstallationDisposition.CREATED, None, "a" * 64)
            installation = CurrentConnectorInstallation("workspace-a", "base", "projection", 1,
                "docker", "connector", original, receipt)
        self.realization = SimpleNamespace(plan=self.plan, registered_products=self.products,
            runtime_authorities=(self.authority,), connector_installation=installation,
            base_graph=SimpleNamespace(graph_descriptor=DEFAULT_GRAPH_CODEC.encode(self.current)),
            desired_graph=SimpleNamespace(graph_descriptor=DEFAULT_GRAPH_CODEC.encode(self.desired)))

    def selection(self):
        return dict(plan=self.plan, current=self.current, desired=self.desired,
            registered_products=self.products, runtime_authorities=(self.authority,))
