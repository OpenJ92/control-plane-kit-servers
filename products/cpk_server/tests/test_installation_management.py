"""Pure managed-child composition; synthetic contracts are not qualified images."""
from dataclasses import replace
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import control_plane_kit_core as core
from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from control_plane_kit_core.receiver_configuration import select_receiver_node_control_configuration_artifact
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology, validate_graph
from control_plane_kit_operations.graph_authoring import product_reference_in_node
from control_plane_kit_servers_cloudflared_connector import managed
from receiver_acceptance_material import AuthoredMaterial
import test_frontend_deployment
from test_managed_postgres_installation import managed_input


ROOT = Path(__file__).resolve().parents[3]


class InstallationManagementTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("control_plane_kit_servers_cpk_server.installation")
        self.assertTrue(hasattr(self.api, "DockerCpkManagement"), "managed installation group is missing")
        # Earlier isolation tests remove gateway modules. Use the same current
        # public value classes as the product factories' exact-type admission.
        control = importlib.import_module("control_plane_kit_servers_cpk_local_gateway.control_configuration")
        relay = importlib.import_module("control_plane_kit_servers_cpk_local_gateway.health_relay_configuration")
        self.transit = importlib.import_module("control_plane_kit_servers_cpk_local_gateway.health_transit_configuration")
        bootstrap = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap")
        self.base = bootstrap._installation(managed_input())
        self.codec = ProductDescriptorCodec()
        self.keys = AuthoredMaterial().public
        self.gateway_id = self.base.installation_id + "-gateway"
        self.gateway = self.document("cpk_local_gateway", relay.gateway_health_declared_runtime_contract())
        self.connector = self.document("cloudflared_connector", managed.declared_runtime_contract())
        self.api_ingress = self.ingress("api", self.base.cpk_node_id, "http-api")
        self.website_ingress = self.ingress("website", self.base.website_node_id, "http")
        self.management_ingress = self.ingress("management", self.gateway_id, "control")
        template = core.ReceiverNodeControlConfigurationCodec().decode_bytes(
            self.base.cpk_product.product.runtime_contract.configuration_artifacts[0].content.encode())
        self.gateway_control = self.configuration(template, self.gateway_id, "1" * 32, control.gateway_control_declaration())
        self.controls = tuple(self.api.DockerCpkConnectorControl(
            ingress_id=ingress.ingress_id,
            configuration=self.configuration(template, ingress.connector_node_id, str(index) * 32, managed.control_declaration()))
            for index, ingress in enumerate((self.api_ingress, self.website_ingress, self.management_ingress), start=2))
        self.trust = self.transit.GatewayHealthTransitConfiguration(self.gateway_control.target, "parent-cpk",
            core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, (self.keys["transit"],))
        self.website_api = importlib.import_module("control_plane_kit_servers_website_server.managed")
        self.website_control = self.configuration(template, self.base.website_node_id, "5" * 32,
            self.website_api.control_declaration())

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

    def managed_website(self, configuration=None, **changes):
        values = dict(image=self.base.website.image, ingress=self.website_ingress,
            connector_product=self.connector, managed_control_configuration=
                self.website_api.control_configuration_artifact(configuration or self.website_control))
        return self.api.DockerCpkWebsite(**{**values, **changes})

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
        self.assertEqual(artifacts["gateway-health-transit"], self.transit.gateway_health_transit_configuration_artifact(self.trust))
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

    def test_managed_website_joins_actual_routes_with_child_api_binding_and_cpk_only_auth(self):
        principals = core.SecretReference("secret://fixture/child-principals")
        artifact = replace(self.website_api.control_configuration_artifact(self.website_control),
            source_digest="a" * 64)
        value = self.installation(website=self.managed_website(managed_control_configuration=artifact),
            control_auth=self.api.MultiPrincipalControlAuth(principals))
        graph = self.graph(value)
        self.assertTrue(validate_graph(graph).valid)
        codec = GraphDescriptorCodec()
        self.assertEqual(codec.encode(codec.decode(codec.encode(graph))), codec.encode(graph))
        website = graph.node(value.website_node_id)
        self.assertEqual(self.receiver(website), self.website_control)
        self.assertEqual(website.configuration_artifacts[0].descriptor(), artifact.descriptor())
        self.assertEqual(website.non_secret_environment()["CPK_WEB_UPSTREAM"], "https://api.example.test")
        self.assertEqual(website.non_secret_environment()["PORT"], "8080")
        self.assertEqual(set(website.endpoints), {"http", "control"})
        gateway = graph.node(self.gateway_id)
        targets = next(item for item in gateway.configuration_artifacts if item.artifact_id == "gateway-health-targets")
        routes = core.ReceiverManagementRoutesCodec().decode_bytes(targets.content.encode())
        self.assertEqual({item.target.node_id.value for item in routes.targets}, set(graph.nodes))
        self.assertEqual(len(routes.targets), 8)
        website_route = next(item for item in routes.targets if item.target.node_id.value == value.website_node_id)
        self.assertEqual(website_route.target, self.website_control.target)
        self.assertEqual(website_route.declaration, self.website_api.control_declaration())
        self.assertEqual(website_route.origin, website.endpoints["control"].address.value)
        self.assertTrue(website_route.origin.endswith(":8000"))
        self.assertTrue(website.endpoints["http"].address.value.endswith(":8080"))
        self.assertEqual({item.ingress_id: item for item in graph.public_ingresses}, {
            item.ingress_id: item for item in (self.api_ingress, self.website_ingress, self.management_ingress)})
        for node in graph.nodes.values():
            self.assertEqual(node.runtime_authority_deliveries, (value.runtime_access,) if node.node_id == value.cpk_node_id else ())
            references = {item.reference for item in node.secret_deliveries}
            self.assertEqual(principals in references, node.node_id == value.cpk_node_id)
        self.assertEqual(website.secret_deliveries, ())
        topology = self.api.compose_docker_cpk_installation(value)
        block = next(child for child in topology.root.children if getattr(child, "block_id", None) == value.website_node_id)
        self.assertEqual(block.implementation.document.product.image, value.website.image)

    def test_managed_website_material_changes_get_distinct_stable_product_identities(self):
        frontend = importlib.import_module("control_plane_kit_servers_cpk_server.client.frontend")
        artifact = self.website_api.control_configuration_artifact(self.website_control)
        image, upstream = self.base.website.image, "https://api.example.test"
        product = frontend.managed_frontend_product(image, upstream=upstream, control_configuration=artifact)
        self.assertNotEqual(product.identity, frontend.frontend_product(image, upstream=upstream).identity)
        for changed_image, changed_upstream, changed_artifact in (
                (replace(image, digest="sha256:" + "d" * 64), upstream, artifact),
                (image, "https://another-child.example.test", artifact),
                (image, upstream, self.website_api.control_configuration_artifact(replace(self.website_control,
                    target=replace(self.website_control.target, receiver_id="6" * 32))))):
            with self.subTest(upstream=changed_upstream, image=changed_image.digest):
                inputs = dict(upstream=changed_upstream, control_configuration=changed_artifact)
                changed = frontend.managed_frontend_product(changed_image, **inputs)
                self.assertNotEqual(changed.identity, product.identity)
                self.assertEqual(changed, frontend.managed_frontend_product(changed_image, **inputs))
                document = self.codec.encode_document(changed)
                self.assertEqual(self.codec.decode_document(document.content), document)

    def test_managed_website_refuses_foreign_scope_or_duplicate_receiver(self):
        roles = core.NodeControlGraphReferenceRole
        for field, role, foreign in (("workspace_id", roles.WORKSPACE, "foreign-workspace"),
                ("runtime_id", roles.RUNTIME, "foreign-runtime"),
                ("node_id", roles.NODE, "foreign-node"),
                ("provider_socket_name", roles.PROVIDER_SOCKET, "http")):
            configuration = replace(self.website_control, target=replace(self.website_control.target,
                **{field: core.NodeControlGraphReference(role, foreign)}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.graph(self.installation(website=self.managed_website(configuration)))
        duplicate = replace(self.website_control, target=replace(self.website_control.target,
            receiver_id=self.gateway_control.target.receiver_id))
        with self.assertRaises(ValueError):
            self.graph(self.installation(website=self.managed_website(duplicate)))

    def test_managed_website_requires_management_and_rejects_invalid_artifact_without_echo(self):
        native = self.base
        with self.assertRaisesRegex(ValueError, "^installation website configuration is invalid$"):
            replace(native, website=replace(native.website, managed_control_configuration=
                self.website_api.control_configuration_artifact(self.website_control)))
        artifact = self.website_api.control_configuration_artifact(self.website_control)
        for changed in (replace(artifact, target_path="/etc/cpk/foreign.json"),
                replace(artifact, content='{"unexpected":"sentinel-private-content"}')):
            with self.subTest(path=changed.target_path), self.assertRaises(ValueError) as raised:
                self.managed_website(managed_control_configuration=changed)
            self.assertEqual(str(raised.exception), "installation website configuration is invalid")
            self.assertIsNone(raised.exception.__context__)

    def test_reopened_assignment_and_image_update_keep_names_and_receiver_artifact(self):
        names = importlib.import_module("control_plane_kit_servers_cpk_server.client.child_names")
        roles = tuple(names.ChildIngressNameBinding(role=role, ingress_id=ingress.ingress_id,
            authority_ref="zone-" + role, lifecycle=ingress.lifecycle)
            for role, ingress in (("api", self.api_ingress), ("website", self.website_ingress),
                                  ("management", self.management_ingress)))
        binding = names.ChildNameBinding(parent_endpoint="https://parent.example.test",
            parent_installation_id="parent-a", parent_workspace_id=self.base.workspace_id,
            child_installation_id=self.base.installation_id, zone_name="example.test", ingresses=roles)
        with TemporaryDirectory() as directory, patch.object(names, "_assignment_root",
                return_value=Path(directory) / ".local" / "state" / "cpk" / "child-installations"):
            assignment = names.create_child_names(binding)
            assigned = {item.role: item.hostname for item in assignment.ingresses}
            api = replace(self.api_ingress, hostname=assigned["api"])
            website = self.managed_website(ingress=replace(self.website_ingress, hostname=assigned["website"]))
            group = self.group(management_ingress=replace(self.management_ingress, hostname=assigned["management"]))
            value = self.installation(group, ingress=api, website=website)
            before = self.graph(value)
            with patch.object(names, "uuid4", side_effect=AssertionError("identity regenerated")):
                self.assertEqual(names.reopen_child_names(binding), assignment)
                self.assertEqual(self.graph(replace(value)), before)
                updated = self.graph(replace(value, website=replace(website,
                    image=replace(website.image, digest="sha256:" + "d" * 64))))
            self.assertEqual(updated.public_ingresses, before.public_ingresses)
            self.assertEqual(self.receiver(updated.node(value.website_node_id)), self.website_control)
            self.assertEqual(updated.node(value.website_node_id).configuration_artifacts,
                before.node(value.website_node_id).configuration_artifacts)
            self.assertEqual(updated.node(value.website_node_id).non_secret_environment()["CPK_WEB_UPSTREAM"],
                "https://" + assigned["api"])

    def test_cross_wired_connector_receiver_is_refused(self):
        first, second, third = self.controls
        crossed = (replace(first, configuration=second.configuration), replace(second, configuration=first.configuration), third)
        with self.assertRaises(ValueError):
            self.graph(self.installation(self.group(connector_controls=crossed)))

    def test_receiver_identity_reused_at_another_valid_node_is_refused(self):
        first, second, third = self.controls
        duplicate = replace(second, configuration=replace(second.configuration,
            target=replace(second.configuration.target, receiver_id=first.configuration.target.receiver_id)))
        with self.assertRaises(ValueError):
            self.graph(self.installation(self.group(connector_controls=(first, duplicate, third))))

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
