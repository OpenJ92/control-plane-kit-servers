"""Wire sizes and catalogue eligibility of the maintained, disposable child composition."""
from dataclasses import replace
import json
import unittest

import httpx2
from jsonschema import Draft202012Validator

from control_plane_kit_core.operations import operator_command_http_routes
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC
from control_plane_kit_servers_cpk_server.request_body import MCP_ENVELOPE_MAX_BYTES
from child_graph_fixture import synthetic_child
from test_standard_mcp import StandardMcpFixture


class ChildWireSizeTests(StandardMcpFixture, unittest.IsolatedAsyncioTestCase):
    def test_invalid_installation_version_sets_are_rejected(self):
        from control_plane_kit_core.secrets import SecretReference

        cases = {
            "missing": lambda versions: versions[:-1],
            "extra": lambda versions: (*versions, replace(versions[0], reference=SecretReference("secret://fixture/extra"))),
            "duplicate": lambda versions: (*versions, versions[0]),
            "conflict": lambda versions: (*versions, replace(versions[0], version_id="another-version")),
        }
        for name, transform in cases.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "^installation secret versions are incomplete or conflicting$"):
                synthetic_child(transform)

    async def test_eight_nodes_six_protected_references_and_exact_wire_sizes(self):
        workspace, desired, docs, uses = synthetic_child()
        expected_versions = {key: "fixture-version-" + str(i) for i, key in enumerate(uses)}
        selected = [choice for node in desired.nodes.values() for choice in node.secret_selections]
        self.assertEqual(len(selected), 7)
        for choice in selected:
            self.assertEqual(choice.version_id, expected_versions[(choice.reference.reference_id, choice.intent.value)])
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

        base = {"workspace_id": workspace, "session_id": "fixture-session", "graph": full,
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
        eligibility = {ref.identity.key: validator.is_valid({"workspace_id": workspace,
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
