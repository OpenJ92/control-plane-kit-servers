"""Same public transport laws with an explicitly read-only server catalogue."""
import unittest

import test_standard_mcp as transport_fixture


READS = {"get_workspace", "get_desired_graph", "get_desired_topology_draft_revision",
    "list_desired_topology_draft_revision_attempts"}


class GrandparentMcpTests(transport_fixture.StandardMcpFixture, unittest.IsolatedAsyncioTestCase):
    mcp_profile = "grandparent-read-only-v1"

    async def test_profile_is_explicit_and_unknown_selection_refuses(self):
        self.assertEqual(self.host.config.mcp_profile, self.mcp_profile)
        with self.assertRaises(self.host.server.BootstrapConfigurationError):
            self.host.server.CpkServerBootstrapConfiguration.from_environment({"CPK_MCP_PROFILE": "readonly-typo"})

    async def test_four_reads_discover_and_agree_with_http_in_both_eras(self):
        for mode in ("auto", "legacy"):
            async with self.client(mode) as client:
                tools = (await client.list_tools()).tools
                self.assertEqual({tool.name for tool in tools}, READS)
                self.assertTrue(all(tool.annotations.read_only_hint for tool in tools))
                for name, arguments, path in (
                    ("get_workspace", {"workspace_id": "workspace-a"}, "/workspaces/workspace-a"),
                    ("get_desired_graph", {"workspace_id": "workspace-a"}, "/workspaces/workspace-a/graphs/desired"),
                    ("get_desired_topology_draft_revision", {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 7},
                     "/workspaces/workspace-a/desired-topology-drafts/draft-a/revisions/7"),
                    ("list_desired_topology_draft_revision_attempts", {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 7},
                     "/workspaces/workspace-a/desired-topology-drafts/draft-a/revisions/7/attempts"),
                ):
                    result = await client.call_tool(name, arguments)
                    expected = await self.http.get(path)
                    self.assertEqual(expected.status_code, 200)
                    self.assertFalse(result.is_error)
                    self.assertEqual(result.structured_content["route_id"], expected.json()["route_id"])
                    self.assertEqual(result.structured_content["principal"], expected.json()["principal"])

    async def test_direct_command_refuses_before_owner_even_without_client_allowlist(self):
        before = sum(len(service.requests) for service in self.host.services.values())
        async with self.client() as client:
            for name in ("prepare_deployment", "register_secret_provider", "provision_secret_material"):
                result = await client.call_tool(name, {})
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content["error"]["status"], 404)
        self.assertEqual(sum(len(service.requests) for service in self.host.services.values()), before)


class GrandparentMcpLifespanTests(transport_fixture.StandardMcpLifespanTests):
    mcp_profile = "grandparent-read-only-v1"
