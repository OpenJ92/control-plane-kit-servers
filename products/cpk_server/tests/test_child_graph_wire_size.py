"""Wire sizes and catalogue eligibility of the maintained, disposable child composition."""
import json
import unittest

import httpx2
from jsonschema import Draft202012Validator

from control_plane_kit_core.operations import operator_command_http_routes
from control_plane_kit_core.products import ProductReference
from control_plane_kit_core.secret_selections import SecretVersionSelection
from control_plane_kit_core.secrets import SecretReference
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph, compile_topology
from control_plane_kit_core.topology.secret_selection import carry_forward_secret_selections
from control_plane_kit_servers_cpk_server.request_body import MCP_ENVELOPE_MAX_BYTES
import test_installation_management as installation_fixture
from test_standard_mcp import StandardMcpFixture


class ChildWireSizeTests(StandardMcpFixture, unittest.IsolatedAsyncioTestCase):
    async def test_eight_nodes_six_protected_references_and_exact_wire_sizes(self):
        fixture = installation_fixture.InstallationManagementTests("test_complete_graph_routes_exact_actual_receivers_and_preserves_documents")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        child = fixture.installation(website=fixture.managed_website(), workspace_grants=(),
            control_auth=fixture.api.MultiPrincipalControlAuth(SecretReference("secret://fixture/principals")),
            workspace_authority=fixture.api.SuppliedChildWorkspaceAuthority(SecretReference("secret://fixture/policy")))
        topology = fixture.api.compose_docker_cpk_installation(child)
        graph = compile_topology(topology)
        docs = {ProductReference.from_document(block.implementation.document): block.implementation.document
                for block in topology.root.children if hasattr(block, "implementation")}
        uses = sorted({(use.reference.reference_id, use.intent.value) for node in graph.nodes.values()
                       for use in node.secret_selections})
        versions = {key: "fixture-version-" + str(i) for i, key in enumerate(uses)}
        choices = {node.node_id: tuple(SecretVersionSelection(use.reference, use.intent,
            versions[(use.reference.reference_id, use.intent.value)]) for use in node.secret_selections)
            for node in graph.nodes.values() if node.secret_selections}
        desired = carry_forward_secret_selections(DeploymentGraph(graph.name), graph, choices,
            product_documents=tuple(docs.values()))
        full = DEFAULT_GRAPH_CODEC.encode(desired)
        self.assertEqual(len(desired.nodes), 8)
        self.assertEqual(len(desired.public_ingresses), 3)
        self.assertIn("secret://fixture/policy", {ref for ref, _ in uses})
        self.assertEqual(set(node.metadata["product_descriptor_digest"] for node in desired.nodes.values()),
                         {ref.descriptor_sha256.value for ref in docs})
        limits = {route.route_id: route.request_schema.max_bytes for route in operator_command_http_routes()}
        samples = []
        inner = httpx2.ASGITransport(app=self.app)
        class Measure(httpx2.AsyncBaseTransport):
            async def handle_async_request(self, request):
                body = await request.aread()
                frame = json.loads(body) if body else {}
                if frame.get("method") == "tools/call":
                    args = frame["params"]["arguments"]
                    samples.append((frame["params"]["name"],
                        len(json.dumps(args, ensure_ascii=True, separators=(",", ":")).encode()), len(body)))
                return await inner.handle_async_request(request)

        base = {"workspace_id": child.workspace_id, "session_id": "fixture-session", "graph": full,
                "receiver_lifecycle": {"current_graph_id": "fixture-current", "current_realized_projection_id": "fixture-current",
                    "desired_graph_id": None, "desired_realized_projection_id": None, "desired_graph_revision": 0}}
        async with httpx2.AsyncClient(transport=Measure(), base_url="http://127.0.0.1:8080",
                headers={"Authorization": "Bearer valid-token"}) as http:
            async with self.client("auto", http=http) as client:
                for name, fields in (("create_desired_topology_draft", {"title": "Child"}),
                        ("revise_desired_topology_draft", {"draft_id": "fixture-draft", "expected_head_revision": 1})):
                    await client.call_tool(name, {**base, **fields, "idempotency_key": "fixture-" + name})
        from control_plane_kit_servers_cpk_server.mcp_adapter import _input_schema
        import_route = next(route for route in operator_command_http_routes() if route.route_id == "command.product.import")
        validator = Draft202012Validator(_input_schema(import_route))
        eligibility = {ref.identity.key: validator.is_valid({"workspace_id": child.workspace_id,
            "idempotency_key": "fixture-import", "imported_at": "2026-10-01T00:00:00Z",
            "descriptor_document": json.loads(doc.content)}) for ref, doc in docs.items()}
        self.assertEqual(len(samples), 2)
        self.assertEqual(len({ref for ref, _ in uses}), 6)
        print("Disposable complete child wire measurement", json.dumps({"nodes": len(desired.nodes), "references": len(uses),
            "graph_bytes": len(json.dumps(full, ensure_ascii=True, separators=(",", ":")).encode()),
            "samples_tool_argument_envelope_bytes": samples,
            "create_limit": limits["command.desired-topology-draft.create"],
            "revise_limit": limits["command.desired-topology-draft.revise"], "envelope_limit": MCP_ENVELOPE_MAX_BYTES,
            "importable_by_exact_product": eligibility}, sort_keys=True))
