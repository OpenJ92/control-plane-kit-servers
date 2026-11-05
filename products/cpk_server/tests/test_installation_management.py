"""Pure managed-child composition; synthetic contracts are not qualified images."""
from dataclasses import replace
import importlib
from pathlib import Path
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from control_plane_kit_core.receiver_configuration import select_receiver_node_control_configuration_artifact
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology, validate_graph
from control_plane_kit_operations.graph_authoring import product_reference_in_node
from control_plane_kit_servers_cloudflared_connector import managed
from control_plane_kit_servers_cpk_local_gateway.control_configuration import gateway_control_declaration
from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import gateway_health_declared_runtime_contract
from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import GatewayHealthTransitConfiguration
from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import gateway_health_transit_configuration_artifact
from receiver_acceptance_material import AuthoredMaterial
import test_frontend_deployment
from test_managed_postgres_installation import managed_input


ROOT = Path(__file__).resolve().parents[3]


class InstallationManagementTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("control_plane_kit_servers_cpk_server.installation")
        self.assertTrue(hasattr(self.api, "DockerCpkManagement"), "managed installation group is missing")
        bootstrap = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")
        self.base = bootstrap._installation(managed_input())
        self.codec = ProductDescriptorCodec()
        self.keys = AuthoredMaterial().public
        self.gateway_id = self.base.installation_id + "-gateway"
        self.gateway = self.document("cpk_local_gateway", gateway_health_declared_runtime_contract())
        self.connector = self.document("cloudflared_connector", managed.declared_runtime_contract())
        self.api_ingress = self.ingress("api", self.base.cpk_node_id, "http-api")
        self.website_ingress = self.ingress("website", self.base.website_node_id, "http")
        self.management_ingress = self.ingress("management", self.gateway_id, "control")
        template = core.ReceiverNodeControlConfigurationCodec().decode_bytes(
            self.base.cpk_product.product.runtime_contract.configuration_artifacts[0].content.encode())
        self.gateway_control = self.configuration(template, self.gateway_id, "1" * 32, gateway_control_declaration())
        self.controls = tuple(self.api.DockerCpkConnectorControl(
            ingress_id=ingress.ingress_id,
            configuration=self.configuration(template, ingress.connector_node_id, str(index) * 32, managed.control_declaration()))
            for index, ingress in enumerate((self.api_ingress, self.website_ingress, self.management_ingress), start=2))
        self.trust = GatewayHealthTransitConfiguration(self.gateway_control.target, "parent-cpk",
            core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, (self.keys["transit"],))

    def document(self, lane, contract):
        original = self.codec.decode_document((ROOT / "products" / lane / "product.cpk.json").read_bytes())
        return self.codec.encode_document(replace(original.product, runtime_contract=contract))

    def ingress(self, role, node, socket):
        return core.NamedPublicIngress(self.base.installation_id + "-" + role,
            core.IngressAuthorityReference("zone-" + role), core.PublicIngressTarget(node, socket),
            self.base.installation_id + "-" + role + "-connector", role + ".example.test")

    def configuration(self, template, node_id, receiver_id, declaration):
        roles = core.NodeControlGraphReferenceRole
        target = core.NodeControlReceiverTarget(
            core.NodeControlGraphReference(roles.WORKSPACE, self.base.workspace_id),
            core.NodeControlGraphReference(roles.RUNTIME, self.base.installation_id + "-docker"),
            core.NodeControlGraphReference(roles.NODE, node_id),
            declaration.surface.provider_socket_name, receiver_id)
        return replace(template, target=target, declaration=declaration)

    def group(self, **changes):
        values = dict(gateway_product=self.gateway, connector_product=self.connector,
            management_ingress=self.management_ingress,
            runtime_management=core.RuntimeManagement(self.gateway_id, self.management_ingress.ingress_id),
            gateway_control=self.gateway_control, transit_trust=self.trust, connector_controls=self.controls)
        return self.api.DockerCpkManagement(**{**values, **changes})

    def installation(self, group=None, **changes):
        values = dict(ingress=self.api_ingress, connector_product=self.connector,
            website=self.api.DockerCpkWebsite(image=self.base.website.image,
                ingress=self.website_ingress, connector_product=self.connector),
            management=self.group() if group is None else group)
        return replace(self.base, **{**values, **changes})

    def graph(self, value=None):
        return compile_topology(self.api.compose_docker_cpk_installation(value or self.installation()))

    def receiver(self, node):
        artifact = select_receiver_node_control_configuration_artifact(
            artifacts=node.configuration_artifacts, environment=node.public_environment,
            control_surfaces=node.block_spec.control_surfaces)
        return core.ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode())

    def test_complete_graph_routes_exact_actual_receivers_and_preserves_documents(self):
        value = self.installation()
        topology = self.api.compose_docker_cpk_installation(value)
        graph = compile_topology(topology)
        self.assertTrue(validate_graph(graph).valid)
        codec = GraphDescriptorCodec()
        self.assertEqual(codec.encode(codec.decode(codec.encode(graph))), codec.encode(graph))
        runtime = graph.runtimes[value.installation_id + "-docker"]
        self.assertEqual(runtime.management, value.management.runtime_management)
        supplied_ingresses = (self.api_ingress, self.website_ingress, self.management_ingress)
        expected = {value.cpk_node_id, value.postgres_node_id, value.secrets_node_id,
            self.gateway_id, *(item.connector_node_id for item in supplied_ingresses)}
        self.assertEqual(set(graph.nodes), expected | {value.website_node_id})
        gateway = graph.node(self.gateway_id)
        artifacts = {item.artifact_id: item for item in gateway.configuration_artifacts}
        self.assertEqual(set(artifacts), {"gateway-control", "gateway-health-targets", "gateway-health-transit"})
        self.assertEqual(self.receiver(gateway), self.gateway_control)
        self.assertEqual(artifacts["gateway-health-transit"], gateway_health_transit_configuration_artifact(self.trust))
        controls = {item.ingress_id: item.configuration for item in self.controls}
        for ingress in supplied_ingresses:
            self.assertEqual(self.receiver(graph.node(ingress.connector_node_id)), controls[ingress.ingress_id])
        routes = core.ReceiverManagementRoutesCodec().decode_bytes(artifacts["gateway-health-targets"].content.encode())
        self.assertEqual(routes.gateway_target, self.gateway_control.target)
        self.assertEqual({item.target.node_id.value for item in routes.targets}, expected)
        self.assertEqual(len(routes.targets), 7)
        for route in routes.targets:
            node = graph.node(route.target.node_id.value)
            configured = self.receiver(node)
            self.assertEqual(route.target, configured.target)
            self.assertEqual(route.declaration, configured.declaration)
            self.assertEqual(route.target.workspace_id.value, value.workspace_id)
            self.assertEqual(route.target.runtime_id.value, runtime.runtime_id)
            self.assertEqual(route.origin, node.endpoints[route.target.provider_socket_name.value].address.value)
        self.assertEqual(graph.node(value.website_node_id).non_secret_environment()["CPK_WEB_UPSTREAM"], "https://api.example.test")
        self.assertEqual(len({item.hostname for item in graph.public_ingresses}), 3)
        self.assertEqual({item.ingress_id: item for item in graph.public_ingresses}, {
            item.ingress_id: item for item in supplied_ingresses})
        for node in graph.nodes.values():
            self.assertEqual(node.runtime_authority_deliveries, (value.runtime_access,) if node.node_id == value.cpk_node_id else ())
        for ingress in graph.public_ingresses:
            node = graph.node(ingress.connector_node_id)
            self.assertEqual(product_reference_in_node(node), ProductReference.from_document(self.connector))
            self.assertEqual(node.secret_deliveries, ())
        self.assertEqual(product_reference_in_node(gateway), ProductReference.from_document(self.gateway))

    def test_cross_wired_connector_receiver_is_refused(self):
        first, second, third = self.controls
        crossed = (replace(first, configuration=second.configuration), replace(second, configuration=first.configuration), third)
        with self.assertRaises(ValueError):
            self.graph(self.installation(self.group(connector_controls=crossed)))

    def test_foreign_gateway_receiver_even_with_matching_trust_is_refused(self):
        roles = core.NodeControlGraphReferenceRole
        target = replace(self.gateway_control.target,
            runtime_id=core.NodeControlGraphReference(roles.RUNTIME, "foreign-runtime"))
        with self.assertRaises(ValueError):
            self.graph(self.installation(self.group(gateway_control=replace(self.gateway_control, target=target),
                transit_trust=replace(self.trust, gateway_target=target))))

    def test_transit_trust_for_another_receiver_is_refused(self):
        with self.assertRaises(ValueError):
            self.graph(self.installation(self.group(transit_trust=replace(self.trust,
                gateway_target=replace(self.gateway_control.target, receiver_id="f" * 32)))))

    def test_incomplete_or_duplicated_connector_controls_are_refused(self):
        for controls in (self.controls[:2], (self.controls[0], self.controls[0], self.controls[2])):
            with self.subTest(controls=len(controls)), self.assertRaises(ValueError):
                self.graph(self.installation(self.group(connector_controls=controls)))

    def test_conflicting_selected_connector_document_is_refused(self):
        conflicting = self.codec.encode_document(replace(self.connector.product,
            image=core.OciImageReference("example.invalid", "other/connector", "sha256:" + "f" * 64)))
        with self.assertRaises(ValueError):
            self.graph(self.installation(connector_product=conflicting))

    def test_wrong_management_target_and_host_collision_are_refused(self):
        for ingress in (replace(self.management_ingress, target=self.api_ingress.target),
                replace(self.management_ingress, hostname=self.api_ingress.hostname)):
            with self.subTest(ingress=ingress.ingress_id), self.assertRaises(ValueError):
                self.graph(self.installation(self.group(management_ingress=ingress)))

    def test_native_disabled_and_standalone_frontend_contracts_are_preserved(self):
        before = self.graph(self.base)
        self.assertEqual(self.graph(replace(self.base, management=None)), before)
        self.assertIsNone(before.runtimes[self.base.installation_id + "-docker"].management)
        frontend = importlib.import_module("control_plane_kit_servers_cpk_server.client.frontend")
        inputs = test_frontend_deployment.FrontendDeploymentTests().inputs()
        ordinary = inputs["connector_product"]
        original_import = __import__

        def without_managed_connector(name, *args, **kwargs):
            if name == "control_plane_kit_servers_cloudflared_connector.managed":
                raise ModuleNotFoundError(name)
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=without_managed_connector):
            website = self.api.DockerCpkWebsite(image=self.base.website.image,
                ingress=self.website_ingress, connector_product=ordinary)
            native = replace(self.base, ingress=self.api_ingress, connector_product=ordinary, website=website)
            native_graph = self.graph(native)
        self.assertEqual({item.ingress_id: item for item in native_graph.public_ingresses}, {
            item.ingress_id: item for item in (self.api_ingress, self.website_ingress)})
        self.assertIsNone(native_graph.runtimes[self.base.installation_id + "-docker"].management)
        inputs["connector_product"] = self.connector
        with self.assertRaises(ValueError):
            frontend.compose_frontend_deployment(**inputs)

