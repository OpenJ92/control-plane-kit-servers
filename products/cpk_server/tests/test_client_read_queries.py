"""Installed-client query values cross the real authenticated HTTP boundary."""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

from control_plane_kit_core.operations import operator_read_http_routes
import test_http_mcp_boundaries as boundary_fixture


class ClientReadQueryTests(unittest.TestCase):
    def setUp(self):
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary
        from control_plane_kit_servers_cpk_server.client.profile import ClientProfile
        from control_plane_kit_servers_cpk_server.client import transport
        self.transport_api = transport
        self.profile_type = ClientProfile
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        credential = root / "credential"
        credential.write_bytes(b"valid-token")
        credential.chmod(0o600)
        self.profile = ClientProfile("http://127.0.0.1:8080", "workspace-a",
            {role: credential for role in ("operator", "approver", "worker")}, root / "state")
        composition, self.services, application, self.verifier = (
            boundary_fixture.CpkServerHttpMcpBoundaryTests()._application())
        self.boundary = CpkServerHttpProcessBoundary(composition, application)
        self.requests = []

    def open_boundary(self, request, *, timeout):
        """Only the socket is replaced; route/auth/query/application remain real."""
        self.requests.append(request)
        parts = urlsplit(request.full_url)
        response = self.boundary.handle(method=request.get_method(), path=parts.path,
            headers=dict(request.header_items()), body=request.data or b"",
            query_string=parts.query.encode("ascii"))
        body = io.BytesIO(json.dumps(response.body).encode())
        if response.status >= 400:
            raise HTTPError(request.full_url, response.status, "boundary refusal", None, body)
        return body

    def test_actual_client_preserves_raw_coordinates_and_structured_queries(self):
        target = {"issuer": "issuer with + space", "subject_id": "operator + name", "kind": "operator"}
        cursor = {"kind": "workspace-permission-history", "installation_id": "installation-a",
            "workspace_id": "workspace-a", "target": target, "after_revision": 1}
        cases = (
            ("read.managed-runtime-assignment", {"runtime_id": "runtime-a", "authority_ref": "authority-a"}),
            ("read.workspace-permission", {"target": target}),
            ("read.workspace-permission-history", {"target": target, "after": cursor, "limit": 2}),
            ("read.receiver-authoring-context", {
                "expected": {"current_graph_id": "graph-current", "current_realized_projection_id": "projection-current",
                    "desired_graph_id": "graph-desired", "desired_realized_projection_id": "projection-desired",
                    "desired_graph_revision": 7},
                "pending_draft": {"draft_id": "draft-a", "expected_head_revision": 3}}),
        )
        with patch.object(self.transport_api, "build_opener",
                return_value=SimpleNamespace(open=self.open_boundary)):
            client = self.transport_api.PublicHttpTransport(self.profile)
            for route, payload in cases:
                with self.subTest(route=route):
                    result = client.call(route, path_parameters={"workspace_id": "workspace-a"},
                        payload=payload, credential_role="operator")
                    self.assertEqual(result["route_id"], route)
                    self.assertEqual(result["payload"], payload)
                    self.assertEqual(result["surface"], "http")
        self.assertEqual(self.verifier.credentials, [b"valid-token"] * len(cases))
        self.assertEqual(len(self.requests), len(cases))

    def test_invalid_or_oversized_query_refuses_before_credentials_and_send(self):
        with patch.object(self.transport_api, "build_opener") as opener, \
                patch.object(self.profile_type, "credential",
                    side_effect=AssertionError("invalid query reached credential acquisition")) as credential:
            client = self.transport_api.PublicHttpTransport(self.profile)
            limit = next(route.request_schema.max_bytes for route in operator_read_http_routes()
                if route.route_id == "read.workspace-permission")
            cases = (
                ("read.managed-runtime-assignment", {"runtime_id": 12, "authority_ref": "authority-a"}),
                ("read.workspace-permissions", {"limit": True}),
                ("read.workspace-permissions", {"limit": 0}),
                ("read.workspace-permission", {"target": []}),
                ("read.workspace-permissions", {"after": []}),
                ("read.workspace-permission", {"target": {"private": float("nan")}}),
                ("read.workspace-permission", {"target": {"private": object()}}),
                ("read.workspace-permission", {"target": {"private": " " * (limit // 2)}}),
            )
            for route, payload in cases:
                with self.subTest(route=route, fields=tuple(payload)):
                    with self.assertRaises(self.transport_api.ClientTransportError) as caught:
                        client.call(route, path_parameters={"workspace_id": "workspace-a"},
                            payload=payload, credential_role="operator")
                    self.assertNotIn("private", str(caught.exception))
                    self.assertIsNone(caught.exception.__context__)
                    self.assertIsNone(caught.exception.__cause__)
            credential.assert_not_called()
            opener.return_value.open.assert_not_called()

    def test_actual_client_preserves_authentication_refusal(self):
        self.profile.credentials["operator"].write_bytes(b"wrong-token")
        with patch.object(self.transport_api, "build_opener",
                return_value=SimpleNamespace(open=self.open_boundary)):
            client = self.transport_api.PublicHttpTransport(self.profile)
            with self.assertRaises(self.transport_api.ClientAuthorizationError):
                client.call("read.workspace-permissions", path_parameters={"workspace_id": "workspace-a"},
                    payload={"limit": 1}, credential_role="operator")
        self.assertTrue(all(not service.requests for service in self.services.values()))
