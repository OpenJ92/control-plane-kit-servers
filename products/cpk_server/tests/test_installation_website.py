"""Same-installation website laws; no image or live serving claim."""
import copy
from dataclasses import FrozenInstanceError, replace
import importlib
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import ProductDescriptorCodec, ProductDescriptorDocument
from control_plane_kit_core.public_ingress import (
    IngressAuthorityReference, NamedPublicIngress, PublicIngressLifecycle, PublicIngressTarget,
)
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology, validate_graph
import test_docker_installation as installation_fixture
import test_frontend_deployment as frontend_fixture
from test_root_bootstrap import installation_input


PACKAGE = "control_plane_kit_servers_cpk_server"
ERROR = "installation website configuration is invalid"


class InstallationWebsiteTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module(PACKAGE + ".installation")
        self.assertTrue(callable(getattr(self.api, "DockerCpkWebsite", None)),
            "installation website interface is missing")
        self.codec = ProductDescriptorCodec()

    def value(self):
        return installation_fixture.DockerInstallationTests().installation(self.api)

    def image(self):
        return frontend_fixture.FrontendDeploymentTests().image()

    def site(self, value, **changes):
        inputs = dict(image=self.image(),
            ingress=NamedPublicIngress("website-public", IngressAuthorityReference("website-zone"),
                PublicIngressTarget(value.installation_id + "-website", "http"),
                "website-connector", "web.example.test", lifecycle=PublicIngressLifecycle.RETAINED),
            connector_product=value.connector_product)
        return self.api.DockerCpkWebsite(**{**inputs, **changes})

    def named(self):
        value = self.value()
        return replace(value, website=self.site(value))

    def external(self):
        value = replace(self.value(), ingress=self.api.ExternalInstallationIngress("https://api.example.test"),
            connector_product=None)
        return replace(value, website=self.api.DockerCpkWebsite(image=self.image(),
            ingress=self.api.ExternalInstallationIngress("https://web.example.test")))

    def compose(self, value):
        return compile_topology(self.api.compose_docker_cpk_installation(value))

    def product(self, value):
        topology = self.api.compose_docker_cpk_installation(value)
        return next(child.implementation.document.product for child in topology.root.children
            if getattr(child, "block_id", None) == value.website_node_id)

    def refused(self, callback):
        with self.assertRaises(ValueError) as raised:
            callback()
        self.assertEqual(str(raised.exception), ERROR)
        self.assertIsNone(raised.exception.__context__)

    def connector(self, selected, **changes):
        return self.codec.encode_document(replace(selected.product,
            runtime_contract=replace(selected.product.runtime_contract, **changes)))

    def test_public_value_and_derived_website_identity_are_frozen_and_closed(self):
        value = self.value()
        site = self.site(value)
        self.assertIs(importlib.import_module(PACKAGE).DockerCpkWebsite, self.api.DockerCpkWebsite)
        self.assertEqual(value.website_node_id, value.installation_id + "-website")
        self.assertEqual(site.image, self.image())
        self.assertNotIn("web.example.test", repr(site))
        with self.assertRaises(FrozenInstanceError):
            site.image = self.image()
        with self.assertRaises(TypeError):
            self.api.DockerCpkWebsite(image=self.image(), ingress=site.ingress,
                connector_product=site.connector_product, upstream="https://foreign.example.test")

    def test_absent_website_preserves_named_external_and_legacy_admission(self):
        named = self.value()
        external = replace(named, ingress=self.api.ExternalInstallationIngress("https://api.example.test/"),
            connector_product=None)
        extended = self.connector(named.connector_product,
            public_environment=(PublicStaticEnvironmentBinding("LEGACY_SETTING", "value"),))
        legacy = replace(named, connector_product=extended)
        for value in (named, external, legacy):
            self.assertIsNone(value.website)
            before = self.compose(value)
            self.assertEqual(self.compose(replace(value, website=None)), before)
            self.assertNotIn(value.website_node_id, before.nodes)
        self.assertEqual(self.compose(legacy).node(legacy.ingress.connector_node_id).non_secret_environment(),
            {"LEGACY_SETTING": "value"})

    def test_absent_root_planning_has_no_frontend_or_optional_runtime_imports(self):
        script = """
import json, sys
from control_plane_kit_servers_cpk_server.bootstrap import plan_root_bootstrap
plan_root_bootstrap(json.loads(sys.stdin.read()), driver_image_id="sha256:" + "a" * 64)
assert "control_plane_kit_servers_cpk_server.client.frontend" not in sys.modules
assert "control_plane_kit_interpreters.docker" not in sys.modules
assert "control_plane_kit_servers_cpk_server.managed_health_configuration" not in sys.modules
"""
        result = subprocess.run([sys.executable, "-c", script], input=json.dumps(installation_input()),
            text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_named_is_one_complete_installation_with_two_exact_ingresses(self):
        value = self.named()
        topology = self.api.compose_docker_cpk_installation(value)
        graph = compile_topology(topology)
        self.assertTrue(validate_graph(graph).valid)
        self.assertEqual(set(graph.nodes), {value.cpk_node_id, value.postgres_node_id, value.secrets_node_id,
            value.website_node_id, value.ingress.connector_node_id, value.website.ingress.connector_node_id})
        self.assertEqual(set(graph.runtimes), {value.installation_id + "-docker"})
        self.assertEqual(topology.root.authority_ref, value.runtime_authority)
        self.assertEqual({item.ingress_id: item for item in topology.public_ingresses},
            {item.ingress_id: item for item in (value.ingress, value.website.ingress)})
        self.assertEqual(graph.edges, self.compose(replace(value, website=None)).edges)
        children = {child.block_id: child for child in topology.root.children if hasattr(child, "block_id")}
        for ingress, selected in ((value.ingress, value.connector_product),
                (value.website.ingress, value.website.connector_product)):
            self.assertEqual(children[ingress.connector_node_id].implementation.document, selected)
        codec = GraphDescriptorCodec()
        encoded = codec.encode(graph)
        self.assertEqual(codec.encode(codec.decode(encoded)), encoded)
        self.assertEqual(codec.encode(self.compose(value)), encoded)

    def test_all_external_has_no_graph_connector_or_ingress_allocations(self):
        value = self.external()
        graph = self.compose(value)
        self.assertTrue(validate_graph(graph).valid)
        self.assertEqual(set(graph.nodes), {value.cpk_node_id, value.postgres_node_id,
            value.secrets_node_id, value.website_node_id})
        self.assertEqual(graph.public_ingresses, ())
        self.assertIsNone(value.connector_product)
        self.assertIsNone(value.website.connector_product)
        self.assertEqual(value.website.ingress.endpoint, "https://web.example.test")
        self.assertEqual(graph.node(value.website_node_id).non_secret_environment(),
            {"CPK_WEB_UPSTREAM": "https://api.example.test", "PORT": "8080"})
        codec = GraphDescriptorCodec()
        self.assertEqual(codec.encode(codec.decode(codec.encode(graph))), codec.encode(graph))

    def test_mixed_profiles_and_wrong_connector_presence_are_refused(self):
        named, external = self.named(), self.external()
        self.refused(lambda: replace(named, website=external.website))
        self.refused(lambda: replace(external, website=named.website))
        self.refused(lambda: replace(named.website, connector_product=None))
        self.refused(lambda: replace(external.website, connector_product=named.connector_product))
        for item in ({}, "private invalid website", False):
            self.refused(lambda: replace(named, website=item))
        # Corrupt only an isolated copy after valid construction. Actual compose
        # must revalidate rather than relying on an earlier dataclass check.
        malformed_site = copy.copy(named.website)
        object.__setattr__(malformed_site, "ingress", external.website.ingress)
        malformed_installation = copy.copy(named)
        object.__setattr__(malformed_installation, "website", malformed_site)
        self.refused(lambda: self.compose(malformed_installation))

    def test_named_targets_and_all_connector_node_collisions_are_refused(self):
        value = self.named()
        reserved = (value.cpk_node_id, value.postgres_node_id, value.secrets_node_id, value.website_node_id,
            value.ingress.connector_node_id)
        for node_id in reserved:
            ingress = replace(value.website.ingress, connector_node_id=node_id)
            self.refused(lambda: replace(value, website=replace(value.website, ingress=ingress)))
        for target in (PublicIngressTarget("foreign-website", "http"),
                PublicIngressTarget(value.website_node_id, "other")):
            ingress = replace(value.website.ingress, target=target)
            self.refused(lambda: replace(value, website=replace(value.website, ingress=ingress)))
        # This alias was valid before the website node became present.
        ingress = replace(value.ingress, connector_node_id=value.website_node_id)
        legacy = replace(value, website=None, ingress=ingress)
        self.compose(legacy)
        self.refused(lambda: replace(legacy, website=value.website))

    def test_ingress_ids_and_hostnames_are_distinct(self):
        value = self.named()
        for changes in ({"ingress_id": value.ingress.ingress_id}, {"hostname": value.ingress.hostname}):
            ingress = replace(value.website.ingress, **changes)
            self.refused(lambda: replace(value, website=replace(value.website, ingress=ingress)))
        external = self.external()
        self.refused(lambda: replace(external, website=replace(external.website, ingress=external.ingress)))

    def test_external_origins_use_existing_canonical_owner_without_normalization(self):
        value = self.external()
        # These values pass the legacy ExternalInstallationIngress constructor;
        # refusals therefore reach the new website profile/canonical owner.
        for endpoint in ("https://private.example.test/", "https://PRIVATE.example.test",
                "https://private.example.test:443", "https://127.1"):
            ingress = self.api.ExternalInstallationIngress(endpoint)
            self.refused(lambda: replace(value, ingress=ingress))
            self.refused(lambda: replace(value, website=replace(value.website, ingress=ingress)))
        updated = replace(value, ingress=self.api.ExternalInstallationIngress("https://api.example.test.:8443"),
            website=replace(value.website, ingress=self.api.ExternalInstallationIngress("https://web.example.test.")))
        self.assertEqual(self.compose(updated).node(updated.website_node_id).non_secret_environment()["CPK_WEB_UPSTREAM"],
            "https://api.example.test.:8443")
        self.assertEqual(updated.website.ingress.endpoint, "https://web.example.test.")

    def test_root_dot_and_port_aliases_cannot_supply_two_ingress_hostnames(self):
        value = self.external()
        frontend = importlib.import_module(PACKAGE + ".client.frontend")
        for endpoint in ("https://api.example.test.", "https://api.example.test:8443",
                "https://api.example.test.:8443"):
            product = frontend.frontend_product(self.image(), upstream=endpoint)
            self.assertEqual(product.runtime_contract.public_environment[0].value, endpoint)
            ingress = self.api.ExternalInstallationIngress(endpoint)
            self.refused(lambda: replace(value, website=replace(value.website, ingress=ingress)))

    def test_strict_frontend_connector_contract_applies_to_both_named_connectors(self):
        base = self.value()
        extra = ConfigurationArtifact("extra", "/etc/cpk/extra.json", ConfigurationMediaType.JSON, "{}")
        for changed in (self.connector(base.connector_product,
                public_environment=(PublicStaticEnvironmentBinding("LEGACY_SETTING", "value"),)),
                self.connector(base.connector_product, configuration_artifacts=(extra,))):
            legacy = replace(base, connector_product=changed)
            self.compose(legacy)
            self.refused(lambda: replace(legacy, website=self.site(base)))
            self.refused(lambda: replace(base, website=self.site(base, connector_product=changed)))
        mismatched = ProductDescriptorDocument(replace(base.connector_product.product, display_name="different"),
            base.connector_product.content)
        self.refused(lambda: self.site(base, connector_product=mismatched))
        self.refused(lambda: self.site(base, connector_product=base.postgres_product))

    def test_existing_api_rejections_keep_their_original_error_owner(self):
        value = self.named()
        mismatched = ProductDescriptorDocument(replace(value.connector_product.product, display_name="different"),
            value.connector_product.content)
        cases = [({"connector_product": value.postgres_product}, "installation selected an incompatible product contract"),
            ({"connector_product": mismatched}, "installation product document must match its canonical contract"),
            ({"ingress": replace(value.ingress, target=PublicIngressTarget(value.cpk_node_id, "other"))},
                "installation ingress must target its CPK HTTP provider"),
            ({"ingress": replace(value.ingress, connector_node_id=value.postgres_node_id)},
                "installation connector identity must be distinct")]
        for changes, error in cases:
            for website in (None, value.website):
                with self.assertRaisesRegex(ValueError, "^" + error + "$"):
                    replace(value, website=website, **changes)

    def test_derived_api_upstream_and_explicit_image_control_website_identity(self):
        value = self.named()
        product = self.product(value)
        self.assertEqual(product.image, value.website.image)
        self.assertEqual({item.name: item.value for item in product.runtime_contract.public_environment},
            {"CPK_WEB_UPSTREAM": "https://" + value.ingress.hostname, "PORT": "8080"})
        self.assertEqual([(item.provider_socket, item.container_port) for item in product.runtime_contract.provider_ports],
            [("http", 8080)])
        image = replace(value.website.image, digest="sha256:" + "b" * 64)
        for updated in (replace(value, website=replace(value.website, image=image)),
                replace(value, ingress=replace(value.ingress, hostname="other-api.example.test"))):
            changed = self.product(updated)
            self.assertNotEqual(changed.identity, product.identity)
            self.assertEqual(changed, self.product(updated))
        self.assertEqual(self.product(value), product)

    def test_website_has_no_authority_secret_or_readiness_claim(self):
        for value in (self.named(), self.external()):
            graph = self.compose(value)
            contract = self.product(value).runtime_contract
            self.assertEqual(contract.sockets.provider_names(), ("http",))
            self.assertEqual(contract.sockets.requirement_names(), ())
            self.assertEqual(contract.secret_deliveries, ())
            self.assertEqual(contract.configuration_artifacts, ())
            self.assertEqual(contract.retained_data_mounts, ())
            self.assertEqual(contract.capabilities, ())
            self.assertEqual(contract.control_surfaces, ())
            self.assertEqual(contract.verification.checks, ())
            self.assertIsNone(contract.gateway_transit)
            for node_id, node in graph.nodes.items():
                self.assertEqual(node.runtime_authority_deliveries,
                    (value.runtime_access,) if node_id == value.cpk_node_id else ())

    def test_backend_and_managed_health_contracts_survive_combined_composition(self):
        from managed_native_material import NativeMaterial
        from control_plane_kit_servers_cpk_server.managed_health_configuration import managed_health_configuration_artifact
        world = NativeMaterial()
        artifact = managed_health_configuration_artifact(json.dumps({"schema": "cpk-server.managed-health.v1",
            "docker": {"socket_path": "/var/run/docker.sock", "request_timeout": 5.0},
            "scopes": [{"workspace_id": "workspace-a", "runtime_id": "docker",
                "authority_ref": world.authority.authority_ref.reference_id}],
            "gateway_documents": [world.authored.documents["gateway"].content.decode()],
            "native_product_document": world.document.content.decode()}).encode())
        base = replace(self.value(), managed_health_configuration=artifact)
        before = self.compose(base)
        enabled = replace(base, website=self.site(base))
        after = self.compose(enabled)
        self.assertEqual(after.edges, before.edges)
        for node_id in before.nodes:
            self.assertEqual(after.node(node_id), before.node(node_id))
        self.assertIn(artifact, after.node(base.cpk_node_id).configuration_artifacts)
        self.assertEqual(enabled.managed_health_configuration.descriptor(), artifact.descriptor())

    def test_pure_composition_and_new_errors_do_not_contact_effects_or_echo_inputs(self):
        base = self.value()
        inputs = dict(image=self.image(), connector_product=base.connector_product,
            ingress=NamedPublicIngress("website-public", IngressAuthorityReference("website-zone"),
                PublicIngressTarget(base.website_node_id, "http"), "website-connector", "web.example.test"))
        with patch("docker.DockerClient") as docker, patch("docker.from_env") as ambient, \
                patch("builtins.open") as files, patch("os.open") as descriptors, \
                patch("socket.getaddrinfo") as network:
            website = self.api.DockerCpkWebsite(**inputs)
            value = replace(base, website=website)
            self.compose(value)
            self.refused(lambda: replace(value, website="private invalid website"))
            self.refused(lambda: self.api.DockerCpkWebsite(image="private unpinned image", ingress=value.website.ingress,
                connector_product=value.connector_product))
            self.refused(lambda: self.api.DockerCpkWebsite(image=self.image(), ingress="private invalid ingress"))
        for effect in (docker, ambient, files, descriptors, network):
            effect.assert_not_called()
