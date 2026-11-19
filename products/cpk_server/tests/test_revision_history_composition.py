"""Installed protocol and transport laws; history semantics remain upstream."""
import json
import unittest
from urllib.parse import quote_from_bytes

from control_plane_kit_core.identity import (
    AuthenticatedPrincipal, PrincipalIdentity, PrincipalKind, WorkspaceGrant,
)
from control_plane_kit_core.operations import (
    ControlPlaneServiceRole, canonical_operator_read_projection_set,
)
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations.cpk_server import CpkServerReadService
from control_plane_kit_servers_cpk_server import (
    CpkServerApplicationBoundary, CpkServerHttpProcessBoundary,
    CpkServerMcpProcessBoundary, create_cpk_server_composition,
)
from test_http_mcp_boundaries import RecordingService


KINDS = ("preparations", "attempts")
PREFIX = "read.desired-topology-draft-revision-"
HTTP_PREFIX = "/workspaces/workspace-a/desired-topology-drafts/draft-a/revisions/7/"
MCP_HEADERS = {"Accept": "application/json", "MCP-Protocol-Version": "2025-06-18",
               "Mcp-Method": "resources/read", "Authorization": "Bearer valid-token"}


class GrantedVerifier:
    """Credential fixture only; workspace authorization uses the real owner."""
    def authenticate(self, credential):
        if credential != b"valid-token":
            raise ValueError("invalid test credential")
        return AuthenticatedPrincipal(
            PrincipalIdentity("https://identity.example.test", "operator-a", PrincipalKind.OPERATOR),
            (WorkspaceGrant("workspace-a", (PolicyScope.INSTANCE_WORKSPACE_READ,)),))


class UnopenedUnitOfWork:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        raise AssertionError("denied or malformed read reached persistence")


class RevisionHistoryCompositionTests(unittest.TestCase):
    def setUp(self):
        self.composition = create_cpk_server_composition()
        routes = {route.route_id for route in self.composition.http_api.routes}
        for kind in KINDS:
            self.assertIn(PREFIX + kind, routes, "accepted revision history route is not installed")

    def boundaries(self, read_service):
        services = {role: RecordingService(role.value) for role in ControlPlaneServiceRole}
        services[ControlPlaneServiceRole.READS] = read_service
        app = CpkServerApplicationBoundary(services, GrantedVerifier())
        return (CpkServerHttpProcessBoundary(self.composition, app),
                CpkServerMcpProcessBoundary(self.composition, app))

    def message(self, name, arguments):
        return {"jsonrpc": "2.0", "id": "history", "method": "resources/read",
                "params": {"name": name, "arguments": arguments}}

    def cursor(self, kind, **scope):
        return {"format_version": 1, "collection": "desired-topology-draft-revision-" + kind,
                "scope": {"workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 7, **scope},
                "position": {"instant": "2026-09-07T00:00:00.000000Z", "item_id": "row-a"}}

    def test_installed_composition_has_exact_read_paths_bindings_and_limits(self):
        bindings = {value.http_route_id: value for value in self.composition.handoff.projection_parity.projections}
        for kind in KINDS:
            route = self.composition.http_api.route(PREFIX + kind)
            self.assertEqual(route.path_template,
                "/workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/revisions/{revision}/" + kind)
            self.assertEqual(route.method.value, "GET")
            self.assertIs(route.service_role, ControlPlaneServiceRole.READS)
            self.assertEqual(bindings[route.route_id].mcp_tool_name,
                             "list_desired_topology_draft_revision_" + kind)
            self.assertEqual(canonical_operator_read_projection_set().projection(route.route_id).max_page_size, 10)

    def test_http_and_both_existing_mcp_names_preserve_scope_limit_and_cursor(self):
        for kind in KINDS:
            recorder = RecordingService("reads")
            http, mcp = self.boundaries(recorder)
            cursor = self.cursor(kind)
            query = b"limit=10&after=" + quote_from_bytes(json.dumps(cursor).encode(), safe="").encode()
            response = http.handle(method="GET", path=HTTP_PREFIX + kind, headers=MCP_HEADERS,
                                   body=b"", query_string=query)
            self.assertEqual(response.status, 200)
            for name in (PREFIX + kind, "list_desired_topology_draft_revision_" + kind):
                response = mcp.handle(headers=MCP_HEADERS, message=self.message(name, {
                    "workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 7,
                    "limit": 10, "after": cursor}))
                self.assertEqual(response.status, 200)
            self.assertEqual(len(recorder.requests), 3)
            first = recorder.requests[0]
            self.assertEqual(first.path_parameters, {"workspace_id": "workspace-a",
                                                    "draft_id": "draft-a", "revision": "7"})
            self.assertEqual(first.payload, {"limit": 10, "after": cursor})
            for request in recorder.requests[1:]:
                self.assertEqual(request.route_id, first.route_id)
                self.assertEqual(request.path_parameters, {})
                self.assertEqual(request.payload, {"workspace_id": "workspace-a",
                    "draft_id": "draft-a", "revision": 7, "limit": 10, "after": cursor})
                self.assertEqual(request.principal, first.principal)

    def test_credentials_fail_before_dispatch_for_both_history_reads(self):
        recorder = RecordingService("reads")
        http, mcp = self.boundaries(recorder)
        for kind in KINDS:
            for token in (None, "expired-token"):
                headers = {key: value for key, value in MCP_HEADERS.items() if key != "Authorization"}
                if token is not None:
                    headers["Authorization"] = "Bearer " + token
                responses = (
                    http.handle(method="GET", path=HTTP_PREFIX + kind, headers=headers,
                                body=b"", query_string=b"limit=malformed"),
                    mcp.handle(headers=headers, message=self.message(PREFIX + kind, {})),
                )
                for response in responses:
                    self.assertEqual(response.status, 401)
                    self.assertNotIn("expired-token", repr(response.body))
        self.assertEqual(recorder.requests, [])

    def test_real_owner_denies_foreign_workspace_before_unit_of_work(self):
        factory = UnopenedUnitOfWork()
        http, mcp = self.boundaries(CpkServerReadService(factory))
        for kind in KINDS:
            responses = (
                http.handle(method="GET", path=HTTP_PREFIX.replace("workspace-a", "workspace-b") + kind,
                            headers=MCP_HEADERS, body=b""),
                mcp.handle(headers=MCP_HEADERS, message=self.message(PREFIX + kind, {
                    "workspace_id": "workspace-b", "draft_id": "draft-a", "revision": 7})),
            )
            for response in responses:
                self.assertEqual(response.status, 403)
                self.assertLess(len(json.dumps(response.body).encode()), 1024)
        self.assertEqual(factory.calls, 0)

    def test_real_owner_rejects_malformed_limits_revisions_and_scoped_cursors_before_uow(self):
        factory = UnopenedUnitOfWork()
        http, mcp = self.boundaries(CpkServerReadService(factory))
        for kind in KINDS:
            for values, query, revision in (
                    ({"limit": 11}, b"limit=11", 7),
                    ({"revision": 0}, b"", 0),
                    ({"after": self.cursor(kind, draft_id="foreign-draft")},
                     b"after=" + quote_from_bytes(json.dumps(self.cursor(kind, draft_id="foreign-draft")).encode(),
                                                   safe="").encode(), 7)):
                responses = (
                    http.handle(method="GET", path=HTTP_PREFIX.replace("/7/", "/" + str(revision) + "/") + kind,
                                headers=MCP_HEADERS, body=b"", query_string=query),
                    mcp.handle(headers=MCP_HEADERS, message=self.message(PREFIX + kind, {
                        "workspace_id": "workspace-a", "draft_id": "draft-a", "revision": 7, **values})),
                )
                for response in responses:
                    self.assertEqual(response.status, 400)
                    self.assertLess(len(json.dumps(response.body).encode()), 1024)
        self.assertEqual(factory.calls, 0)
