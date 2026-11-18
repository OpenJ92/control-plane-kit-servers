"""Authored-value laws only; never image qualification or Docker effects."""
from dataclasses import replace
import unittest

import control_plane_kit_core as core

from docker_declaration_update import declaration_documents, declaration_graph, current_route_intent
from docker_image_update_material import DockerImageMaterial, IMAGES


class DockerDeclarationMaterialTests(unittest.TestCase):
    def test_pair_changes_only_declaration_default_and_revision_on_one_image_value(self):
        material = DockerImageMaterial("workspace-a")
        # A real historical reference is inert test data here, never claimed to
        # support this family or used to execute the new live scenario.
        both, ready = declaration_documents(material, IMAGES["hello_b"]["reference"])
        original = material.successor.product
        self.assertEqual(replace(both.product, identity=original.identity, image=original.image), original)
        self.assertEqual(both.product.image, ready.product.image)
        self.assertEqual(ready.product.identity.contract_revision, both.product.identity.contract_revision + 1)
        before, after = both.product.runtime_contract, ready.product.runtime_contract
        old, = [value for value in before.configuration_artifacts if value.artifact_id == "hello-control"]
        new, = [value for value in after.configuration_artifacts if value.artifact_id == "hello-control"]
        codec = core.ReceiverNodeControlConfigurationCodec()
        first, second = (codec.decode_bytes(value.content.encode()) for value in (old, new))
        self.assertEqual(second.declaration.surface.health_reads, (core.NodeHealthReadKind.READINESS,))
        self.assertEqual(replace(second, declaration=first.declaration), first)
        self.assertNotEqual(old.content_digest, new.content_digest)
        self.assertEqual(replace(after, control_surfaces=before.control_surfaces,
            configuration_artifacts=tuple(old if value.artifact_id == old.artifact_id else value
                for value in after.configuration_artifacts)), before)
        self.assertEqual(replace(ready.product, identity=both.product.identity, runtime_contract=before), both.product)

    def test_desired_surface_and_full_routes_leave_selected_material_for_authoring(self):
        material = DockerImageMaterial("workspace-a")
        _, ready = declaration_documents(material, IMAGES["hello_b"]["reference"])
        graph = declaration_graph(material.a, ready)
        before, after = material.a.node("api"), graph.node("api")
        self.assertEqual(after.configuration_artifacts, before.configuration_artifacts)
        self.assertEqual(after.secret_selections, before.secret_selections)
        self.assertEqual(after.block_spec.control_surfaces, ready.product.runtime_contract.control_surfaces)
        for name in ("gateway", "api-y", "connector"):
            self.assertEqual(graph.node(name), material.a.node(name))
        intent = current_route_intent(graph)
        artifact, = [value for value in graph.node("gateway").configuration_artifacts
            if value.artifact_id == "gateway-health-targets"]
        routes = core.ReceiverManagementRoutesCodec().decode_bytes(artifact.content.encode())
        self.assertEqual(tuple((value.target_id, value.target_scope.node_id, value.target_scope.provider_socket_name,
            value.origin) for value in intent.targets), tuple((value.target_id, value.target.node_id.value,
            value.target.provider_socket_name.value, value.origin) for value in routes.targets))

    def test_foreign_repository_and_mutable_tag_are_not_candidate_inputs(self):
        material = DockerImageMaterial("workspace-a")
        for reference in ("ghcr.io/openj92/control-plane-kit-servers/hello-server:latest",
                IMAGES["gateway"]["reference"]):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                declaration_documents(material, reference)
