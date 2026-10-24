"""#255 material and placement laws; actual OCI evidence belongs to the live gate."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from control_plane_kit_core.planning import StartNode, NodeTarget
from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from control_plane_kit_core.runtime_effects import RuntimeEffectResult, RuntimeProductMaterial
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
from control_plane_kit_interpreters.docker.sdk import DockerSdkClient

from docker_image_update_material import DockerImageMaterial, IMAGES, image_value
from image_identity_test_material import qualified_images
from docker_image_update_placement import OwnedControllerPlacement, PREFIX
from docker_image_update_ports import CompletedRuntimeCall, FixtureBoundaryFailure
from docker_receiver_reintroduction import DockerReintroductionMaterial, route_intent, with_nodes
from test_docker_image_update_ports import completed


class ContainmentTests(unittest.TestCase):
    def setUp(self):
        self.graph = DockerImageMaterial("workspace-a").a
        self.graph = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(self.graph))

    def test_removal_filters_runtime_order_after_codec_roundtrip(self):
        expected = tuple(name for name in self.graph.runtimes["docker"].children if name != "api-y")
        changed = with_nodes(self.graph, {name: node for name, node in self.graph.nodes.items()
            if name != "api-y"})
        self.assertEqual(changed.runtimes["docker"].children, expected)
        self.assertEqual(changed.node("api"), self.graph.node("api"))
        self.assertEqual(changed.public_ingresses, self.graph.public_ingresses)

    def test_introduction_appends_without_reordering_retained_children(self):
        original = self.graph.runtimes["docker"].children
        retained = tuple(name for name in original if name != "api-y")
        without = replace(self.graph, nodes={name: node for name, node in self.graph.nodes.items()
            if name != "api-y"}, runtimes={"docker": replace(self.graph.runtimes["docker"], children=retained)})
        without = DEFAULT_GRAPH_CODEC.decode(DEFAULT_GRAPH_CODEC.encode(without))
        changed = with_nodes(without, {**without.nodes, "api-y": self.graph.node("api-y")})
        self.assertEqual(changed.runtimes["docker"].children, (*retained, "api-y"))

    def test_one_immutable_product_supplies_two_unauthored_instances(self):
        material = DockerReintroductionMaterial("workspace-a")
        x, y = material.graph.node("api"), material.graph.node("api-y")
        self.assertEqual(material.documents["api"], material.documents["api-y"])
        self.assertEqual(x.metadata, y.metadata)
        self.assertEqual(x.block_spec.control_surfaces, y.block_spec.control_surfaces)
        self.assertFalse(x.configuration_artifacts or y.configuration_artifacts)
        self.assertEqual(x.public_environment, y.public_environment)
        self.assertNotEqual(x.endpoints, y.endpoints)
        self.assertEqual(material.a.runtimes["docker"].children, ("gateway", "connector"))
        self.assertEqual(material.graph.runtimes["docker"].children, ("gateway", "connector", "api", "api-y"))
        self.assertEqual(material.expected_start_roles["api"], "hello_family")
        self.assertEqual(material.expected_start_roles["api-y"], "hello_family")
        self.assertEqual(material.documents["api"].product.image.execution_reference,
            IMAGES["hello_family"]["reference"])
        self.assertNotEqual(material.introductions[0].scope, material.introductions[1].scope)
        self.assertEqual(len(route_intent(material.graph).targets), 3)


class SelectedStartImageTests(unittest.TestCase):
    def fixture(self, role="hello_family", *, expected_role=None):
        engine = Mock()
        sdk = DockerSdkClient(client=Mock(), connect_on_init=False)
        sdk.inspect_container = Mock()
        sdk.close = Mock()
        engine.info.return_value = {"ID": "daemon-a"}
        product = DockerImageMaterial("workspace-a").documents["api-y"].product
        document = ProductDescriptorCodec().encode_document(replace(product,
            image=image_value(IMAGES[role]["reference"])))
        request = replace(completed().request, operation=StartNode(NodeTarget("api")),
            products=(RuntimeProductMaterial("api", "docker", ProductReference.from_document(document),
                document.product),))
        container = SimpleNamespace(id="c" * 64, labels={PREFIX + "workspace": "workspace-a",
            PREFIX + "runtime": "docker", PREFIX + "kind": "container", PREFIX + "node": "api"},
            attrs={"Image": IMAGES[role]["image_id"], "Config": {"User": IMAGES[role]["user"]}})
        engine.containers.get.return_value = container
        sdk.inspect_container.return_value = SimpleNamespace(container_id=container.id, running=True,
            network_attachments=(SimpleNamespace(network_id="n" * 64),))
        placement = OwnedControllerPlacement(engine, sdk, "workspace-a", "b" * 64, "daemon-a",
            expected_start_roles={} if expected_role is None else {"api": expected_role},
            qualified_images=qualified_images())
        placement.network_id = "n" * 64
        record = CompletedRuntimeCall(request, RuntimeEffectResult.succeeded(request.effect_id,
            evidence={"runtime_id": "docker", "container": container.id}))
        return placement, record, container

    def test_reviewed_family_passes_observed_and_committed_start_checks(self):
        placement, record, container = self.fixture(expected_role="hello_family")
        placement.starting(record.request)
        placement.observed(record)
        self.assertEqual(placement.record["containers"][container.id]["image_role"], "hello_family")
        placement.completed(record)
        self.assertEqual(placement.inspect_node("api").container_id, container.id)

    def test_expected_role_must_match_selected_product_before_dispatch(self):
        placement, record, _ = self.fixture(expected_role="hello_a")
        with self.assertRaises(FixtureBoundaryFailure):
            placement.starting(record.request)
        self.assertFalse(placement.record["intents"])

    def test_default_start_and_strict_image_user_owner_network_checks_remain(self):
        placement, record, _ = self.fixture("hello_a")
        placement.starting(record.request)
        placement.observed(record)
        placement.completed(record)
        for invalid in ("image", "user", "owner", "network"):
            with self.subTest(invalid=invalid):
                placement, record, container = self.fixture(expected_role="hello_family")
                if invalid == "image":
                    container.attrs["Image"] = "sha256:" + "0" * 64
                elif invalid == "user":
                    container.attrs["Config"]["User"] = "root"
                elif invalid == "owner":
                    container.labels[PREFIX + "workspace"] = "foreign"
                else:
                    placement.sdk.inspect_container.return_value.network_attachments = ()
                with self.assertRaises(FixtureBoundaryFailure):
                    placement.observed(record)

    def test_unknown_roles_refuse_and_expected_roles_cannot_drift(self):
        placement, _, _ = self.fixture(expected_role="hello_family")
        with self.assertRaises(TypeError):
            placement.expected_start_roles["api"] = "hello_a"
        with self.assertRaises(FixtureBoundaryFailure):
            self.fixture(expected_role="unreviewed-image")
