"""#243 pure website composition; fixture images are not published artifacts."""

from dataclasses import replace
import importlib
from pathlib import Path
import unittest

from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import (
    OciImageReference, OciPlatform, ProductDescriptorCodec, ProductDescriptorDocument,
)
from control_plane_kit_core.public_ingress import (
    IngressAuthorityReference, NamedPublicIngress, PublicIngressLifecycle, PublicIngressTarget,
)
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology, validate_graph


ROOT = Path(__file__).resolve().parents[3]
MODULE = "control_plane_kit_servers_cpk_server.client.frontend"


class FrontendDeploymentTests(unittest.TestCase):
    def api(self):
        try:
            return importlib.import_module(MODULE)
        except ModuleNotFoundError as error:
            if error.name != MODULE:
                raise
            self.fail("#243 pure frontend composition is not implemented")

    def image(self):
        # Synthetic identity used only as pure test data, never pulled or published.
        return OciImageReference("example.invalid", "fixture/website", "sha256:" + "a" * 64,
                                 platforms=(OciPlatform("linux", "amd64"),),
                                 provenance={"fixture": "not-a-built-image"})

    def inputs(self):
        return dict(
            image=self.image(), upstream="https://cpk.example.test",
            workspace_id="frontend-workspace", runtime_id="frontend-runtime",
            network_name="cpk-frontend-network", authority_ref=RuntimeAuthorityReference("local-docker"),
            ingress=NamedPublicIngress(
                "frontend-public", IngressAuthorityReference("zone-authority"),
                PublicIngressTarget("website", "http"), "frontend-connector", "web.example.test",
                lifecycle=PublicIngressLifecycle.EPHEMERAL),
            connector_product=ProductDescriptorCodec().decode_document(
                (ROOT / "products/cloudflared_connector/product.cpk.json").read_bytes()),
        )

    def test_product_preserves_explicit_image_and_exact_unverified_serving_contract(self):
        api = self.api()
        product = api.frontend_product(self.image(), upstream="https://cpk.example.test")
        self.assertEqual(product.image, self.image())
        contract = product.runtime_contract
        self.assertEqual({item.name: item.value for item in contract.public_environment},
                         {"CPK_WEB_UPSTREAM": "https://cpk.example.test", "PORT": "8080"})
        self.assertEqual([(p.provider_socket, p.container_port) for p in contract.provider_ports],
                         [("http", 8080)])
        self.assertEqual(contract.sockets.provider_names(), ("http",))
        self.assertEqual(contract.sockets.requirement_names(), ())
        self.assertEqual(contract.verification.checks, ())
        self.assertEqual(contract.capabilities, ())
        self.assertEqual(contract.control_surfaces, ())
        self.assertIsNone(contract.gateway_transit)
        self.assertEqual(contract.secret_deliveries, ())
        self.assertEqual(contract.configuration_artifacts, ())
        self.assertEqual(contract.retained_data_mounts, ())
        codec = ProductDescriptorCodec()
        document = codec.encode_document(product)
        self.assertEqual(codec.decode_document(document.content), document)

    def test_material_changes_have_distinct_product_identity_and_matching_port(self):
        api = self.api()
        base = api.frontend_product(self.image(), upstream="https://cpk.example.test")
        for image, origin, port in (
            (self.image(), "https://cpk.example.test", 10443),
            (self.image(), "https://other.example.test:8443", 8080),
            (replace(self.image(), digest="sha256:" + "b" * 64), "https://cpk.example.test", 8080),
        ):
            with self.subTest(origin=origin, port=port, digest=image.digest):
                product = api.frontend_product(image, upstream=origin, port=port)
                self.assertNotEqual(product.identity, base.identity)
                self.assertEqual(product.runtime_contract.provider_ports[0].container_port, port)
                self.assertEqual({p.name: p.value for p in product.runtime_contract.public_environment}["PORT"], str(port))
                self.assertEqual(product, api.frontend_product(image, upstream=origin, port=port))

    def test_rejects_noncanonical_or_credential_bearing_origins_without_echo(self):
        api = self.api()
        for origin in (
            "http://cpk.example.test", "https://user:secret@cpk.example.test", "https://CPK.example.test",
            "https://cpk.example.test/", "https://cpk.example.test/path", "https://cpk.example.test?token=secret",
            "https://cpk.example.test#secret", "https://cpk.example.test:443", "https://cpk.example.test:08080",
            "https://cpk.example.test\\evil", "https://cpk.example.test\n", "https://127.1",
            "https://0x7f000001", "https://cpk.123", "https://%63pk.example.test", "", None,
        ):
            with self.subTest(origin=origin):
                with self.assertRaisesRegex(ValueError, "^frontend upstream must be a canonical HTTPS origin$"):
                    api.frontend_product(self.image(), upstream=origin)

    def test_accepts_canonical_origins_and_rejects_invalid_ports_or_unpinned_image(self):
        api = self.api()
        for origin in ("https://cpk.example.test", "https://cpk.example.test:8443", "https://127.0.0.1", "https://[::1]:8443"):
            with self.subTest(origin=origin):
                self.assertEqual(api.frontend_product(self.image(), upstream=origin).runtime_contract.public_environment[0].value, origin)
        for port in (True, "8080", 1023, 65536, None):
            with self.subTest(port=port), self.assertRaises(ValueError):
                api.frontend_product(self.image(), upstream="https://cpk.example.test", port=port)
        with self.assertRaises(TypeError):
            api.frontend_product("website:latest", upstream="https://cpk.example.test")

    def test_graph_roundtrip_preserves_explicit_ingress_connector_and_runtime_scope(self):
        api = self.api()
        inputs = self.inputs()
        topology = api.compose_frontend_deployment(**inputs, port=9090)
        graph = compile_topology(topology)
        self.assertTrue(validate_graph(graph).valid)
        self.assertEqual(graph.workspace_id, inputs["workspace_id"])
        self.assertEqual(set(graph.nodes), {"website", "frontend-connector"})
        self.assertEqual(set(graph.runtimes), {"frontend-runtime"})
        self.assertEqual(topology.root.authority_ref, inputs["authority_ref"])
        self.assertIsNone(topology.root.management)
        self.assertEqual(topology.public_ingresses, (inputs["ingress"],))
        children = {child.block_id: child for child in topology.root.children}
        self.assertEqual(children["frontend-connector"].implementation.document, inputs["connector_product"])
        self.assertEqual(children["website"].implementation.document.product.image, inputs["image"])
        for node in graph.nodes.values():
            self.assertEqual(node.runtime_authority_deliveries, ())
        self.assertEqual(graph.node("website").block_spec.verification.checks, ())
        codec = GraphDescriptorCodec()
        encoded = codec.encode(graph)
        self.assertEqual(codec.encode(codec.decode(encoded)), encoded)
        self.assertEqual(codec.encode(compile_topology(api.compose_frontend_deployment(**inputs, port=9090))), encoded)

    def test_wrong_ingress_target_or_aliased_node_identity_refuses(self):
        api = self.api()
        inputs = self.inputs()
        for target in (PublicIngressTarget("website", "other"), PublicIngressTarget("frontend-connector", "http")):
            with self.subTest(target=target), self.assertRaises(ValueError):
                api.compose_frontend_deployment(**{**inputs, "ingress": replace(inputs["ingress"], target=target)})
        with self.assertRaises(TypeError):
            api.compose_frontend_deployment(**{**inputs, "authority_ref": "local-docker"})

    def test_connector_document_cannot_disagree_with_selected_contract(self):
        api = self.api()
        inputs = self.inputs()
        selected = inputs["connector_product"]
        mismatched = ProductDescriptorDocument(replace(selected.product, display_name="different"), selected.content)
        with self.assertRaises(ValueError):
            api.compose_frontend_deployment(**{**inputs, "connector_product": mismatched})
        foreign = ProductDescriptorCodec().encode_document(api.frontend_product(self.image(), upstream=inputs["upstream"]))
        with self.assertRaises(ValueError):
            api.compose_frontend_deployment(**{**inputs, "connector_product": foreign})

    def test_composition_contains_only_frontend_scope_not_hello_or_root_resources(self):
        api = self.api()
        topology = api.compose_frontend_deployment(**self.inputs())
        graph = compile_topology(topology)
        self.assertEqual(graph.workspace_id, "frontend-workspace")
        self.assertEqual({node.runtime_id for node in graph.nodes.values()}, {"frontend-runtime"})
        self.assertEqual(graph.edges, {})
        self.assertEqual([(i.ingress_id, i.target.node_id, i.connector_node_id) for i in graph.public_ingresses],
                         [("frontend-public", "website", "frontend-connector")])
        # Retention is workspace separation, not a claim that normal later cleanup is forbidden.
        self.assertEqual(graph.public_ingresses[0].lifecycle, PublicIngressLifecycle.EPHEMERAL)
