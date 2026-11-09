"""Complete-child pair and fixture lifetime laws; no completed Operations truth."""
from contextlib import contextmanager
from pathlib import Path
import os
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from control_plane_kit_core.http_verification_sample_installation import HttpVerificationSampleReceiverConfigurationCodec
from control_plane_kit_core.http_verification_samples import http_verification_check_digest
from control_plane_kit_core.planning import ReviewChange, WaitForHealthy
from control_plane_kit_core.products import OciImageReference, ProductReference
from control_plane_kit_core.secret_selections import SecretVersionSelection, secret_selections_from_descriptor
from control_plane_kit_servers_secrets_server import configuration as secrets
from control_plane_kit_servers_cpk_server import control_configuration as cpk
from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import (
    ARTIFACT_ID as GATEWAY_SAMPLE_ARTIFACT_ID, gateway_http_sample_trust_from_artifact,
)
from http_sample_installation_assembly import assemble, image_options, IMAGE_ROLES


@contextmanager
def isolated_directory():
    previous = Path.cwd()
    with TemporaryDirectory(prefix="cpk181-pair-law-") as directory:
        root = Path(directory)
        os.chdir(root)
        try:
            yield root
        finally:
            os.chdir(previous)
    assert not root.exists(), "fixture directory cleanup failed"


class FullInstallationHttpSampleTests(unittest.TestCase):
    def images(self):
        # Public synthetic unit metadata only; no image is acquired/qualified.
        return {role: OciImageReference("example.invalid", "fixture/selected-" + role,
            "sha256:" + str(index) * 64) for index, role in enumerate(sorted(IMAGE_ROLES), start=1)}

    def test_full_image_selection_refuses_incomplete_or_conflicting_inputs_before_fixture_setup(self):
        images = self.images()
        invalid = [{role:value for role, value in images.items() if role != missing} for missing in images]
        invalid.extend(({}, images | {"unknown":images["cpk"]}, images | {"gateway":None},
            images | {"gateway":"unqualified:tag"}))
        with patch("http_sample_installation_assembly.InstallationManagementTests.setUp") as setup:
            for candidate in invalid:
                with self.subTest(roles=tuple(candidate)), self.assertRaises(ValueError):
                    assemble(images=candidate)
            with self.assertRaises(ValueError):
                assemble(images=images, postgres_image=images["postgres"])
            setup.assert_not_called()

    def test_full_image_selection_joins_all_products_before_graph_and_preserves_obligations(self):
        images = self.images()
        with isolated_directory():
            fixture, original, baseline, graph, gateway_document, plan = assemble(images=images)
        connectors = (original.ingress.connector_node_id, original.website.ingress.connector_node_id,
            original.management.management_ingress.connector_node_id)
        expected = {original.cpk_node_id:"cpk", original.postgres_node_id:"postgres",
            original.secrets_node_id:"secrets", original.website_node_id:"website",
            original.management.runtime_management.gateway_node_id:"gateway",
            **{node:"connector" for node in connectors}}
        self.assertEqual(set(graph.nodes), set(expected))
        documents = {ProductReference.from_document(document).descriptor_sha256.value:document.product
            for document in fixture.product_documents}
        for node_id, role in expected.items():
            self.assertEqual(documents[graph.node(node_id).metadata["product_descriptor_digest"]].image, images[role])
            self.assertEqual(graph.node(node_id).block_spec.verification, baseline.node(node_id).block_spec.verification)
        self.assertEqual(gateway_document.product.image, images["gateway"])
        self.assertEqual(original.secrets_product.product.image, images["secrets"])
        self.assertEqual(original.connector_product, original.website.connector_product)
        self.assertEqual(original.connector_product, original.management.connector_product)
        self.assertEqual(graph.edges, baseline.edges)
        self.assertEqual(graph.runtimes, baseline.runtimes)
        self.assertEqual(graph.public_ingresses, baseline.public_ingresses)
        self.assertEqual(len(graph.public_ingresses), 3)
        self.assertEqual(len([edge for edge in graph.edges.values()
            if edge.provider_role == original.postgres_node_id and edge.consumer_role == original.cpk_node_id]), 4)
        self.assertEqual({entry.operation.target.node_id for entry in plan.activities
            if type(entry.operation) is WaitForHealthy},
            {original.cpk_node_id, original.secrets_node_id, original.postgres_node_id})
        self.assertEqual([check.check_id for check in graph.node(original.cpk_node_id).block_spec.verification.checks], ["live", "ready"])
        self.assertEqual([check.check_id for check in graph.node(original.secrets_node_id).block_spec.verification.checks], ["live", "ready"])
        self.assertEqual([check.check_id for check in graph.node(original.postgres_node_id).block_spec.verification.checks], ["installation-postgres-ready"])

    def test_full_image_environment_is_closed_and_preserves_legacy_postgres_selection(self):
        images = self.images()
        encoded = {role:value.descriptor() for role, value in images.items()}
        self.assertEqual(image_options({"CPK_SOURCE_ASSEMBLY_IMAGES":json.dumps(encoded)}), {"images":images})
        legacy = json.dumps(images["postgres"].descriptor())
        self.assertEqual(image_options({"CPK_SOURCE_ASSEMBLY_POSTGRES_IMAGE":legacy}), {"postgres_image":images["postgres"]})
        self.assertEqual(image_options({}), {"postgres_image":None})
        for invalid in (encoded | {"gateway":None}, {key:value for key, value in encoded.items() if key != "gateway"}):
            with self.assertRaises(ValueError):
                image_options({"CPK_SOURCE_ASSEMBLY_IMAGES":json.dumps(invalid)})
        with self.assertRaises(ValueError):
            image_options({"CPK_SOURCE_ASSEMBLY_IMAGES":json.dumps(encoded), "CPK_SOURCE_ASSEMBLY_POSTGRES_IMAGE":legacy})

    def test_complete_assembly_preserves_supplied_product_image_and_exact_versions(self):
        # Unit metadata only; this fixture reference is never an acquired image.
        image = OciImageReference("example.invalid", "fixture/selected-postgres", "sha256:" + "7" * 64)
        with isolated_directory():
            _, _, _, unselected, _, _ = assemble()
            uses = sorted({(entry.reference, entry.intent) for node in unselected.nodes.values()
                for entry in node.secret_selections}, key=lambda pair: (pair[0].reference_id, pair[1].value))
            versions = tuple(SecretVersionSelection(reference, intent, "synthetic-version-" + str(index))
                for index, (reference, intent) in enumerate(uses))
            fixture, original, baseline, graph, _, _ = assemble(postgres_image=image, secret_versions=versions)
        postgres = graph.node(original.postgres_node_id)
        self.assertEqual(original.postgres_product.product.image, image)
        topology = fixture.api.compose_docker_cpk_installation(original)
        postgres_instance, = (node for node in topology.root.children
            if getattr(node, "block_id", None) == original.postgres_node_id)
        reference = ProductReference.from_document(postgres_instance.implementation.document)
        self.assertEqual(postgres.metadata["product_descriptor_digest"], reference.descriptor_sha256.value)
        self.assertEqual(postgres.block_spec.verification, baseline.node(postgres.node_id).block_spec.verification)
        self.assertEqual(graph.edges, baseline.edges)
        self.assertEqual(len(graph.nodes), 8)
        self.assertEqual(len(graph.public_ingresses), 3)
        for node_id, node in graph.nodes.items():
            choices = fixture.secret_version_choices.get(node_id, [])
            self.assertEqual(node.secret_selections, secret_selections_from_descriptor(choices))
            self.assertTrue(all(type(value) is SecretVersionSelection for value in node.secret_selections))
        password = lambda node: next(value for value in graph.node(node).secret_selections
            if value.reference == original.postgres_password)
        self.assertEqual(password(original.postgres_node_id), password(original.cpk_node_id))

    def test_secrets_companion_covers_original_pair_and_removes_only_its_review(self):
        with isolated_directory():
            fixture, original, baseline, graph, _, plan = assemble()
        before, actual = baseline.node(original.secrets_node_id), graph.node(original.secrets_node_id)
        companions = [item for item in actual.configuration_artifacts
            if item.artifact_id == secrets.HTTP_SAMPLE_SLOT.artifact_id]
        self.assertEqual(len(companions), 1, "Secrets full companion is missing from the actual installation")
        configured = HttpVerificationSampleReceiverConfigurationCodec().decode_canonical_bytes(
            companions[0].content.encode("utf-8"))
        self.assertEqual(configured.target, fixture.receiver(before).target)
        self.assertEqual(configured.declaration_identity, fixture.receiver(before).declaration.identity().value)
        self.assertEqual([(entry.check_id, entry.check_digest) for entry in configured.checks],
            [(check.check_id, http_verification_check_digest(check)) for check in before.block_spec.verification.checks])
        self.assertEqual(actual.block_spec.verification, before.block_spec.verification)
        self.assertEqual(actual.secret_deliveries, before.secret_deliveries)
        self.assertEqual(actual.sockets, before.sockets)
        self.assertEqual(set(graph.nodes), set(baseline.nodes))
        self.assertEqual(graph.edges, baseline.edges)
        self.assertEqual(graph.runtimes, baseline.runtimes)
        self.assertEqual(graph.public_ingresses, baseline.public_ingresses)
        reviews = [activity.operation.target.subject.node_id for activity in plan.activities
            if type(activity.operation) is ReviewChange]
        self.assertEqual(reviews, [original.postgres_node_id], "only the independent SQL refusal should remain")
        self.assertFalse(plan.ready_for_execution)

    def test_fixture_keeps_matching_synthetic_signers_until_owned_cleanup(self):
        with isolated_directory() as root:
            custody = root / "commissioning"
            custody.mkdir(mode=0o700)
            fixture, original, _, graph, _, _ = assemble(commissioning_directory=custody)
            installed = []
            for node_id, slot in ((original.cpk_node_id, cpk.HTTP_SAMPLE_SLOT),
                                  (original.secrets_node_id, secrets.HTTP_SAMPLE_SLOT)):
                artifact, = (entry for entry in graph.node(node_id).configuration_artifacts
                    if entry.artifact_id == slot.artifact_id)
                configured = HttpVerificationSampleReceiverConfigurationCodec().decode_canonical_bytes(artifact.content.encode())
                self.assertEqual(configured.verifier.issuer, "parent-cpk")
                self.assertEqual(configured.verifier.public_keys, (fixture.sample_signing_material.public["workload"],))
                installed.append(("workload", configured.verifier.public_keys[0]))
            gateway = graph.node(original.management.runtime_management.gateway_node_id)
            artifact, = (entry for entry in gateway.configuration_artifacts
                if entry.artifact_id == GATEWAY_SAMPLE_ARTIFACT_ID)
            trust = gateway_http_sample_trust_from_artifact(artifact)
            self.assertEqual(trust.issuer, "parent-cpk")
            self.assertEqual(trust.gateway_target, original.management.gateway_control.target)
            self.assertEqual(trust.public_keys, (fixture.sample_signing_material.public["transit"],))
            self.assertNotEqual(trust.public_keys[0].fingerprint_sha256, fixture.keys["transit"].fingerprint_sha256,
                "sample transit and health transit must have separate signers")
            installed.append(("transit", trust.public_keys[0]))
            for family, key in installed:
                private = serialization.load_pem_private_key(fixture.sample_signing_material.private[family], password=None)
                public = serialization.load_pem_public_key(key.public_key_pem.encode("ascii"))
                public.verify(private.sign(b"isolated-fixture-lifetime"), b"isolated-fixture-lifetime")
            for purpose, filename in (("workload-node-control-surface-read", "surface-read.pem"),
                                      ("workload-node-health-read", "health-read.pem")):
                path = custody / filename
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_mode & 0o777, 0o400)
                private = serialization.load_pem_private_key(path.read_bytes(), password=None)
                for node_id in (original.cpk_node_id, original.secrets_node_id, original.postgres_node_id):
                    verifier, = (entry for entry in fixture.receiver(graph.node(node_id)).verifiers
                        if entry.purpose.value == purpose)
                    public = serialization.load_pem_public_key(verifier.public_keys[0].public_key_pem.encode("ascii"))
                    public.verify(private.sign(b"isolated-commissioning-lifetime"), b"isolated-commissioning-lifetime")
        self.assertFalse(custody.exists())
