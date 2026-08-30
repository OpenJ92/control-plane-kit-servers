import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.parse import quote_from_bytes

from starlette.datastructures import Headers
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.identity import (
    AuthenticatedPrincipal,
    PrincipalIdentity,
    PrincipalKind,
)


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"


class RecordingService:
    def __init__(self, name: str) -> None:
        self.name = name
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        return {
            "service": self.name,
            "route_id": request.route_id,
            "surface": request.surface,
            "path_parameters": request.path_parameters,
            "payload": request.payload,
            "principal": request.principal.descriptor(),
        }


class CredentialRejected(ValueError):
    pass


class DeterministicVerifier:
    def __init__(self) -> None:
        self.credentials = []

    def authenticate(self, credential: bytes) -> AuthenticatedPrincipal:
        self.credentials.append(credential)
        if credential == b"valid-token":
            return _principal()
        if credential == b"expired-token":
            raise CredentialRejected("credential expired: expired-token")
        if credential == b"wrong-audience-token":
            raise CredentialRejected("wrong audience: wrong-audience-token")
        raise CredentialRejected(f"invalid credential: {credential!r}")


class CpkServerHttpMcpBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(PRODUCT_SRC))

    def tearDown(self) -> None:
        sys.path.remove(str(PRODUCT_SRC))
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith(
                "control_plane_kit_servers_cpk_server."
            ):
                sys.modules.pop(name, None)

    def _application(self):
        from control_plane_kit_servers_cpk_server import (
            CpkServerApplicationBoundary,
            CpkServerProcessConfiguration,
            create_cpk_server_composition,
        )

        composition = create_cpk_server_composition(
            CpkServerProcessConfiguration.execution_capable(
                authentication_required=True
            )
        )
        services = {
            role: RecordingService(role.value)
            for role in ControlPlaneServiceRole
        }
        verifier = DeterministicVerifier()
        return composition, services, CpkServerApplicationBoundary(services, verifier), verifier

    def _require_raw_query_boundary(self, http) -> None:
        self.assertIn(
            "query_string",
            inspect.signature(http.handle).parameters,
            "HTTP boundary does not accept the raw ASGI query string",
        )

    @staticmethod
    def _read_events_message(arguments: dict[str, object]) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "id": "run-events-1",
            "method": "resources/read",
            "params": {
                "name": "read.run-events",
                "arguments": arguments,
            },
        }

    @staticmethod
    def _mcp_read_headers() -> dict[str, str]:
        return {
            "Accept": "application/json",
            "MCP-Protocol-Version": "2025-06-18",
            "Mcp-Method": "resources/read",
            "Authorization": "Bearer valid-token",
        }

    def test_http_paged_read_query_matches_mcp_application_request(self) -> None:
        from control_plane_kit_servers_cpk_server import (
            CpkServerHttpProcessBoundary,
            CpkServerMcpProcessBoundary,
        )

        composition, services, application, _ = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)
        mcp = CpkServerMcpProcessBoundary(composition, application)
        self._require_raw_query_boundary(http)
        cursor = {"opaque": {"sequence": 2}, "version": 1}
        encoded_cursor = quote_from_bytes(
            b'{ "version": 1, "opaque": {"sequence": 2} }',
            safe="",
        ).encode("ascii")

        http_response = http.handle(
            method="GET",
            path="/workspaces/workspace-a/runs/run-a/events",
            query_string=b"limit=100&after=" + encoded_cursor,
            headers={"Authorization": "Bearer valid-token"},
            body=b"",
        )
        mcp_response = mcp.handle(
            headers=self._mcp_read_headers(),
            message=self._read_events_message(
                {
                    "workspace_id": "workspace-a",
                    "run_id": "run-a",
                    "limit": 100,
                    "after": cursor,
                }
            ),
        )

        self.assertEqual(http_response.status, 200)
        self.assertEqual(mcp_response.status, 200)
        http_request, mcp_request = services[ControlPlaneServiceRole.READS].requests
        self.assertEqual(http_request.route_id, "read.run-events")
        self.assertEqual(mcp_request.route_id, "read.run-events")
        self.assertEqual(
            {**http_request.path_parameters, **http_request.payload},
            dict(mcp_request.payload),
        )
        self.assertEqual(http_request.payload, {"limit": 100, "after": cursor})
        self.assertEqual(http_request.principal, mcp_request.principal)

    def test_http_query_decoder_owns_transport_shape_not_operations_semantics(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application, _ = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)
        self._require_raw_query_boundary(http)
        opaque_cursor = {"not-an-operations-cursor": {"still": "an object"}}
        encoded_cursor = quote_from_bytes(
            json.dumps(opaque_cursor).encode("utf-8"),
            safe="",
        ).encode("ascii")

        response = http.handle(
            method="GET",
            path="/workspaces/workspace-a/runs/run-a/events",
            query_string=b"limit=101&after=" + encoded_cursor,
            headers={"Authorization": "Bearer valid-token"},
            body=b"",
        )

        self.assertEqual(response.status, 200)
        request = services[ControlPlaneServiceRole.READS].requests[0]
        self.assertEqual(request.payload, {"limit": 101, "after": opaque_cursor})

    def test_http_after_accepts_equivalent_json_object_serializations(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application, _ = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)
        self._require_raw_query_boundary(http)
        documents = (
            b'{"alpha":1,"nested":{"beta":2}}',
            b'{ "nested" : { "beta" : 2 }, "alpha" : 1 }',
        )

        for document in documents:
            with self.subTest(document=document):
                response = http.handle(
                    method="GET",
                    path="/workspaces/workspace-a/runs/run-a/events",
                    query_string=b"after="
                    + quote_from_bytes(document, safe="").encode("ascii"),
                    headers={"Authorization": "Bearer valid-token"},
                    body=b"",
                )
                self.assertEqual(response.status, 200)

        self.assertEqual(
            [
                request.payload
                for request in services[ControlPlaneServiceRole.READS].requests
            ],
            [
                {"after": {"alpha": 1, "nested": {"beta": 2}}},
                {"after": {"alpha": 1, "nested": {"beta": 2}}},
            ],
        )

    def test_http_read_query_rejects_closed_grammar_violations(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application, _ = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)
        self._require_raw_query_boundary(http)
        nested: object = {"leaf": "bounded"}
        for _ in range(65):
            nested = {"next": nested}
        nested_query = b"after=" + quote_from_bytes(
            json.dumps(nested).encode("utf-8"),
            safe="",
        ).encode("ascii")
        cases = (
            b"limit=1&limit=2",
            b"l%69mit=1&limit=2",
            b"after=%7B%7D&after=%7B%7D",
            b"a%66ter=%7B%7D&after=%7B%7D",
            b"unknown=value",
            b"workspace_id=workspace-a",
            b"run_id=run-a",
            b"limit=",
            b"limit=0",
            b"limit=-1",
            b"limit=%2B1",
            b"limit=01",
            b"limit=1.0",
            b"after=%",
            b"after=%0",
            b"after=%GG",
            b"after=%FF",
            b"after=%7B",
            b"after=%5B%5D",
            b"after=null",
            b"after=%22text%22",
            b"after=1",
            b"after=%7B%22key%22%3A1%2C%22key%22%3A2%7D",
            (
                b"after=%7B%22outer%22%3A%7B%22key%22%3A1%2C"
                b"%22key%22%3A2%7D%7D"
            ),
            b"after=%7B%22value%22%3ANaN%7D",
            b"after=%7B%22value%22%3AInfinity%7D",
            b"after=%7B%22value%22%3A-Infinity%7D",
            b"credential=must-not-reflect",
            nested_query,
        )
        for query_string in cases:
            with self.subTest(query_string=query_string[:80]):
                response = http.handle(
                    method="GET",
                    path="/workspaces/workspace-a/runs/run-a/events",
                    query_string=query_string,
                    headers={"Authorization": "Bearer valid-token"},
                    body=b"",
                )
                self.assertEqual(response.status, 400)
                message = response.body["error"]["message"]
                self.assertIsInstance(message, str)
                self.assertLessEqual(len(message), 64)
                rendered = repr(response.body).lower()
                for forbidden in ("workspace-a", "run-a", "credential", "reflect"):
                    self.assertNotIn(forbidden, rendered)

        self.assertEqual(services[ControlPlaneServiceRole.READS].requests, [])

    def test_http_query_size_body_and_command_fail_before_decode_or_dispatch(self) -> None:
        import control_plane_kit_servers_cpk_server.boundary as boundary_module
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application, _ = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)
        self._require_raw_query_boundary(http)
        route = composition.http_api.route("read.run-events")
        self.assertEqual(
            route.path_template,
            "/workspaces/{workspace_id}/runs/{run_id}/events",
        )
        max_bytes = route.request_schema.max_bytes
        prefix = b"after=%7B%22padding%22%3A%22"
        suffix = b"%22%7D"
        self.assertGreater(max_bytes, len(prefix) + len(suffix))
        at_limit = (
            prefix
            + (b"a" * (max_bytes - len(prefix) - len(suffix)))
            + suffix
        )
        over_limit = (
            prefix
            + (b"a" * (max_bytes + 1 - len(prefix) - len(suffix)))
            + suffix
        )
        self.assertEqual(len(at_limit), max_bytes)
        self.assertEqual(len(over_limit), max_bytes + 1)

        accepted = http.handle(
            method="GET",
            path="/workspaces/workspace-a/runs/run-a/events",
            query_string=at_limit,
            headers={"Authorization": "Bearer valid-token"},
            body=b"",
        )
        self.assertEqual(accepted.status, 200)
        self.assertEqual(
            len(
                services[ControlPlaneServiceRole.READS]
                .requests[0]
                .payload["after"]["padding"]
            ),
            max_bytes - len(prefix) - len(suffix),
        )
        services[ControlPlaneServiceRole.READS].requests.clear()

        with patch.object(
            boundary_module.json,
            "loads",
            side_effect=AssertionError("oversized query reached JSON decoding"),
        ) as loads:
            oversized = http.handle(
                method="GET",
                path="/workspaces/workspace-a/runs/run-a/events",
                query_string=over_limit,
                headers={"Authorization": "Bearer valid-token"},
                body=b"",
            )
        self.assertEqual(oversized.status, 413)
        loads.assert_not_called()

        body_on_read = http.handle(
            method="GET",
            path="/workspaces/workspace-a/runs/run-a/events",
            query_string=b"limit=1",
            headers={"Authorization": "Bearer valid-token"},
            body=b"{}",
        )
        query_on_command = http.handle(
            method="POST",
            path="/workspaces/workspace-a/plans",
            query_string=b"limit=1",
            headers={"Authorization": "Bearer valid-token"},
            body=b'{"change":"blue-to-green"}',
        )

        self.assertEqual(body_on_read.status, 400)
        self.assertEqual(query_on_command.status, 400)
        self.assertTrue(all(service.requests == [] for service in services.values()))

    def test_http_query_authentication_precedes_sensitive_decode_and_reflection(
        self,
    ) -> None:
        import control_plane_kit_servers_cpk_server.boundary as boundary_module
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application, verifier = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)
        self._require_raw_query_boundary(http)
        query_string = (
            b"after=%7B%22token%22%3A%22credential-do-not-disclose%22%7D"
        )

        with patch.object(
            boundary_module.json,
            "loads",
            side_effect=AssertionError("unauthenticated query was decoded"),
        ) as loads:
            response = http.handle(
                method="GET",
                path="/workspaces/workspace-a/runs/run-a/events",
                query_string=query_string,
                headers={"Authorization": "Bearer invalid-token"},
                body=b"",
            )

        self.assertEqual(response.status, 401)
        self.assertEqual(
            response.body,
            {"error": {"status": 401, "message": "invalid credential"}},
        )
        self.assertNotIn("token", repr(response.body).lower())
        self.assertNotIn("credential-do-not-disclose", repr(response.body))
        loads.assert_not_called()
        self.assertEqual(verifier.credentials, [b"invalid-token"])
        self.assertTrue(all(service.requests == [] for service in services.values()))

    def test_product_local_law_cards_assign_814_owned_laws(self) -> None:
        import json

        cards = json.loads(
            (ROOT / "products" / "cpk_server" / "law-cards" / "extract-f-814.json")
            .read_text(encoding="utf-8")
        )

        self.assertEqual(cards["schema"], "cpk-server.extract-f-law-cards")
        self.assertEqual(cards["issue"], "#814")
        self.assertEqual(
            [card["law"] for card in cards["law_cards"]],
            [
                "behavior.configured-token-protects-control-routes",
                "behavior.control-routes-can-be-called-without-token-when-unconfigured",
                "behavior.execution-auth-does-not-protect-ordinary-data-routes",
                "behavior.execution-mutation-body-is-bounded-before-application",
                "behavior.observers-route-mutates-state",
                "behavior.unknown-active-target-returns-bad-request",
            ],
        )
        self.assertTrue(
            all(card["owner"] == "control-plane-kit-servers/cpk_server" for card in cards["law_cards"])
        )

    def test_http_read_route_delegates_to_shared_reads_service(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application, verifier = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)

        response = http.handle(
            method="GET",
            path="/workspaces/workspace-a/graphs/current",
            headers={"Authorization": "Bearer valid-token"},
            body=b"",
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["service"], "reads")
        self.assertEqual(response.body["route_id"], "read.current-graph")
        self.assertEqual(response.body["surface"], "http")
        self.assertEqual(response.body["path_parameters"], {"workspace_id": "workspace-a"})
        self.assertEqual(response.body["principal"], _principal().descriptor())
        self.assertEqual(verifier.credentials, [b"valid-token"])
        self.assertEqual(len(services[ControlPlaneServiceRole.READS].requests), 1)

    def test_http_command_route_requires_auth_and_delegates_to_planning(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application, _ = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)

        rejected = http.handle(
            method="POST",
            path="/workspaces/workspace-a/plans",
            headers={},
            body=b'{"change":"blue-to-green"}',
        )
        accepted = http.handle(
            method="POST",
            path="/workspaces/workspace-a/plans",
            headers={"Authorization": "Bearer present"},
            body=b'{"change":"blue-to-green"}',
        )

        self.assertEqual(rejected.status, 401)
        self.assertNotIn("Bearer present", repr(rejected.body))
        self.assertEqual(accepted.status, 401)
        self.assertNotIn("Bearer present", repr(accepted.body))
        self.assertEqual(len(services[ControlPlaneServiceRole.PLANNING].requests), 0)

    def test_invalid_credentials_fail_before_dispatch_and_are_redacted(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application, verifier = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)

        cases = (
            {},
            {"Authorization": "Bearer"},
            {"Authorization": "Bearer "},
            {"Authorization": "Basic valid-token"},
            {"Authorization": "Bearer expired-token"},
            {"Authorization": "Bearer wrong-audience-token"},
            {"Authorization": "Bearer invalid-token"},
            {"Authorization": "Bearer valid-token", "authorization": "Bearer valid-token"},
            Headers(
                raw=[
                    (b"authorization", b"Bearer valid-token"),
                    (b"authorization", b"Bearer valid-token"),
                ]
            ),
            {"Authorization": "Bearer " + ("x" * 4097)},
        )
        for headers in cases:
            with self.subTest(headers=tuple(headers)):
                response = http.handle(
                    method="POST",
                    path="/workspaces/workspace-a/plans",
                    headers=headers,
                    body=b'{"credential":"must-not-be-decoded"}',
                )
                self.assertEqual(response.status, 401)
                self.assertEqual(response.body["error"]["message"], "invalid credential")
                self.assertNotIn("token", repr(response.body))

        self.assertEqual(services[ControlPlaneServiceRole.PLANNING].requests, [])
        self.assertEqual(
            verifier.credentials,
            [b"expired-token", b"wrong-audience-token", b"invalid-token"],
        )

    def test_bearer_scheme_and_header_name_are_case_insensitive_by_contract(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application, verifier = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)

        response = http.handle(
            method="GET",
            path="/workspaces/workspace-a/graphs/current",
            headers={"authorization": "bEaReR valid-token"},
            body=b"",
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(verifier.credentials, [b"valid-token"])
        self.assertEqual(len(services[ControlPlaneServiceRole.READS].requests), 1)

    def test_verifier_exception_is_not_retained_by_bounded_error(self) -> None:
        from control_plane_kit_servers_cpk_server import (
            CredentialAuthenticationError,
            authenticate_bearer_credential,
        )

        verifier = DeterministicVerifier()
        with self.assertRaises(CredentialAuthenticationError) as raised:
            authenticate_bearer_credential(
                {"Authorization": "Bearer invalid-token"},
                verifier,
            )

        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__)
        self.assertNotIn("invalid-token", repr(raised.exception))

    def test_http_malformed_and_oversized_payloads_fail_before_services(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        composition, services, application, _ = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)

        malformed = http.handle(
            method="POST",
            path="/workspaces/workspace-a/plans",
            headers={"Authorization": "Bearer valid-token"},
            body=b'{',
        )
        oversized = http.handle(
            method="POST",
            path="/workspaces/workspace-a/plans",
            headers={"Authorization": "Bearer valid-token"},
            body=b'{"x":"' + (b"a" * 70000) + b'"}',
        )

        self.assertEqual(malformed.status, 400)
        self.assertEqual(oversized.status, 413)
        self.assertEqual(services[ControlPlaneServiceRole.PLANNING].requests, [])

    def test_mcp_tools_call_uses_same_application_boundary_as_http(self) -> None:
        from control_plane_kit_servers_cpk_server import (
            CpkServerHttpProcessBoundary,
            CpkServerMcpProcessBoundary,
        )

        composition, services, application, verifier = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)
        mcp = CpkServerMcpProcessBoundary(composition, application)

        self.assertIs(http.application, mcp.application)

        result = mcp.handle(
            headers={
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
                "Mcp-Method": "tools/call",
                "Authorization": "Bearer valid-token",
            },
            message={
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {
                    "name": "command.deployment.plan",
                    "arguments": {"workspace_id": "workspace-a", "change": "green"},
                },
            },
        )

        self.assertEqual(result.status, 200)
        self.assertEqual(result.body["result"]["service"], "planning")
        self.assertEqual(result.body["result"]["surface"], "mcp")
        self.assertEqual(result.body["result"]["principal"], _principal().descriptor())
        self.assertEqual(verifier.credentials, [b"valid-token"])
        self.assertEqual(len(services[ControlPlaneServiceRole.PLANNING].requests), 1)

    def test_mcp_resources_read_uses_read_service_and_auth_failures_are_bounded(self) -> None:
        from control_plane_kit_servers_cpk_server import CpkServerMcpProcessBoundary

        composition, services, application, _ = self._application()
        mcp = CpkServerMcpProcessBoundary(composition, application)

        missing_auth = mcp.handle(
            headers={
                "Accept": "application/json",
                "MCP-Protocol-Version": "2025-06-18",
                "Mcp-Method": "resources/read",
            },
            message={
                "jsonrpc": "2.0",
                "id": "read-1",
                "method": "resources/read",
                "params": {"name": "read.current-graph", "arguments": {"workspace_id": "workspace-a"}},
            },
        )
        accepted = mcp.handle(
            headers={
                "Accept": "application/json",
                "MCP-Protocol-Version": "2025-06-18",
                "Mcp-Method": "resources/read",
                "Authorization": "Bearer valid-token",
            },
            message={
                "jsonrpc": "2.0",
                "id": "read-1",
                "method": "resources/read",
                "params": {"name": "read.current-graph", "arguments": {"workspace_id": "workspace-a"}},
            },
        )

        self.assertEqual(missing_auth.status, 401)
        self.assertEqual(accepted.status, 200)
        self.assertEqual(accepted.body["result"]["service"], "reads")
        self.assertEqual(len(services[ControlPlaneServiceRole.READS].requests), 1)

    def test_unknown_http_and_mcp_operations_fail_closed(self) -> None:
        from control_plane_kit_servers_cpk_server import (
            CpkServerHttpProcessBoundary,
            CpkServerMcpProcessBoundary,
        )

        composition, services, application, _ = self._application()
        http = CpkServerHttpProcessBoundary(composition, application)
        mcp = CpkServerMcpProcessBoundary(composition, application)

        http_response = http.handle(
            method="GET",
            path="/workspaces/workspace-a/not-real",
            headers={"Authorization": "Bearer valid-token"},
            body=b"",
        )
        mcp_response = mcp.handle(
            headers={
                "Accept": "application/json",
                "MCP-Protocol-Version": "2025-06-18",
                "Mcp-Method": "tools/call",
                "Authorization": "Bearer valid-token",
            },
            message={
                "jsonrpc": "2.0",
                "id": "bad-1",
                "method": "tools/call",
                "params": {"name": "command.not-real", "arguments": {}},
            },
        )

        self.assertEqual(http_response.status, 404)
        self.assertEqual(mcp_response.status, 404)
        self.assertTrue(all(service.requests == [] for service in services.values()))

    def test_application_errors_map_to_bounded_process_responses(self) -> None:
        from control_plane_kit_operations import CpkServerApplicationError
        from control_plane_kit_servers_cpk_server import CpkServerHttpProcessBoundary

        class FailingService:
            def handle(self, request):
                raise CpkServerApplicationError(503, "store unavailable")

        composition, services, application, verifier = self._application()
        services[ControlPlaneServiceRole.READS] = FailingService()
        application = type(application)(services, verifier)
        http = CpkServerHttpProcessBoundary(composition, application)

        response = http.handle(
            method="GET",
            path="/workspaces/workspace-a/graphs/current",
            headers={"Authorization": "Bearer valid-token"},
            body=b"",
        )

        self.assertEqual(response.status, 503)
        self.assertEqual(response.body["error"]["message"], "store unavailable")


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        PrincipalIdentity(
            issuer="https://identity.openj92.dev",
            subject_id="operator-jacob",
            kind=PrincipalKind.OPERATOR,
        )
    )


if __name__ == "__main__":
    unittest.main()
