"""Public test inputs built by the maintained installation composer with synthetic coordinates."""
import json
from pathlib import Path

from control_plane_kit_core.products import ProductReference
from control_plane_kit_core.secret_selections import SecretVersionSelection, secret_selections_from_descriptor
from control_plane_kit_core.secrets import SecretReference
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph, compile_topology
from control_plane_kit_core.topology.secret_selection import carry_forward_secret_selections
import test_installation_management as installation_fixture


def synthetic_child(transform_versions=tuple):
    fixture = installation_fixture.InstallationManagementTests("test_complete_graph_routes_exact_actual_receivers_and_preserves_documents")
    fixture.setUp()
    try:
        child = fixture.installation(website=fixture.managed_website(), workspace_grants=(),
            control_auth=fixture.api.MultiPrincipalControlAuth(SecretReference("secret://fixture/principals")),
            workspace_authority=fixture.api.SuppliedChildWorkspaceAuthority(SecretReference("secret://fixture/policy")))
        topology = fixture.api.compose_docker_cpk_installation(child)
        graph = compile_topology(topology)
        docs = {ProductReference.from_document(block.implementation.document): block.implementation.document
                for block in topology.root.children if hasattr(block, "implementation")}
        uses = sorted({(use.reference.reference_id, use.intent.value) for node in graph.nodes.values()
                       for use in node.secret_selections})
        identities = {(use.reference.reference_id, use.intent.value): (use.reference, use.intent)
                      for node in graph.nodes.values() for use in node.secret_selections}
        versions = tuple(SecretVersionSelection(*identities[key], "fixture-version-" + str(i))
                         for i, key in enumerate(uses))
        author = getattr(fixture.api, "installation_secret_version_choices", None)
        if author is None:
            raise AssertionError("whole-installation secret version authoring is missing")
        choices = {node: secret_selections_from_descriptor(entries)
                   for node, entries in author(child, transform_versions(versions)).items()}
        desired = carry_forward_secret_selections(DeploymentGraph(graph.name), graph, choices,
            product_documents=tuple(docs.values()))
        return child.workspace_id, desired, docs, uses
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    # Only ordinary input documents cross into the selected authoring test image.
    workspace, graph, docs, _ = synthetic_child()
    bundle = {"workspace": workspace, "graph": DEFAULT_GRAPH_CODEC.encode(graph),
              "products": [json.loads(doc.content) for doc in docs.values()]}
    Path("/tmp/cpk-synthetic-child.json").write_text(json.dumps(bundle), encoding="utf-8")
