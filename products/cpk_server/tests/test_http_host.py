"""Actual CPK application routing, and representative SDK composition laws."""
from dataclasses import replace
import importlib
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException
from control_plane_kit_core import NodeHealthReadKind
from control_plane_kit_core.operations import ControlPlaneServiceRole, HttpApiContract, HttpMethod

from test_http_mcp_boundaries import DeterministicVerifier, RecordingService
from cpk_http_host_fixtures import fixture, install_control, token

PRODUCT_SRC = Path(__file__).resolve().parents[1] / "src"
UNKNOWN = {"error": {"status":404, "message":"unknown route"}}


class CpkHttpHostTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(PRODUCT_SRC))
        self.server = importlib.import_module("control_plane_kit_servers_cpk_server.server")
        self.services = {role:RecordingService(role.value) for role in ControlPlaneServiceRole}
        self.verifier = DeterministicVerifier()
        environ = {
            "CPK_SERVER_MODE":"execution-capable", "CPK_CONTROL_AUTH_CONFIGURED":"true",
            "CPK_PORT":"8080", "CPK_RUNTIME_INTERPRETERS":"none",
            **{f"CPK_{store}_DATABASE_URL":"postgres://fixture:fixture@database.invalid/db"
               for store in ("WORKPLACE", "ACTIVITY_HISTORY", "OBSERVER_STATE", "GRAPH_TOPOLOGY")},
        }
        config = self.server.CpkServerBootstrapConfiguration.from_environment(environ)
        # Replace only effectful service construction; use the real app and boundaries.
        with patch.object(self.server, "_operations_application", return_value=SimpleNamespace(services=self.services)):
            self.app = self.server.create_app(config, self.verifier)

    def tearDown(self):
        sys.path.remove(str(PRODUCT_SRC))
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith("control_plane_kit_servers_cpk_server."):
                sys.modules.pop(name, None)

    def assert_no_service_work(self):
        self.assertEqual([request for service in self.services.values() for request in service.requests], [])

    def test_every_operator_contract_reaches_unchanged_auth_boundary(self):
        routes = self.app.state.http_boundary.composition.http_api.routes
        self.assertEqual(len(routes), 74)
        with TestClient(self.app, follow_redirects=False) as client:
            for route in routes:
                path = re.sub(r"\{[^}]+\}", "fixture", route.path_template)
                with self.subTest(method=route.method, path=path):
                    response = client.request(str(route.method), path, headers={"Authorization":"Bearer rejected"}, content=b"invalid JSON")
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json(), {"error":{"status":401, "message":"invalid credential"}})
        self.assertEqual(self.verifier.credentials, [b"rejected"] * len(routes))
        self.assert_no_service_work()

    def test_exact_workspace_command_and_raw_query_use_existing_dispatch(self):
        boundary = self.app.state.http_boundary
        cases = (
            ("POST", "/workspaces", b'{"workspace_id":"fixture"}'),
            ("GET", "/workspaces/workspace-a/runs/run-a/events?limit=100&after=%7B%22version%22%3A1%2C%22opaque%22%3A%7B%22sequence%22%3A2%7D%7D", b""),
        )
        headers = {"Authorization":"Bearer valid-token"}
        with TestClient(self.app) as client:
            for method, url, body in cases:
                path, _, query = url.partition("?")
                expected = boundary.handle(method=method, path=path, query_string=query.encode(), body=body, headers=headers)
                response = client.request(method, url, content=body, headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), json.loads(json.dumps(expected.body)))
        requests = [request for service in self.services.values() for request in service.requests]
        self.assertEqual(len(requests), 4)

    def test_public_unknown_methods_slashes_and_legacy_health_compatibility(self):
        with TestClient(self.app, follow_redirects=False) as client:
            for path in ("/", "/unknown", "/workspaces/", "/workspaces/fixture/unknown", "/health", "/health/", "/health/unknown", "/health/live/", "/health/ready/", "/mcp/", "/mcp/unknown"):
                for method in ("GET", "POST"):
                    with self.subTest(method=method, path=path):
                        response = client.request(method, path)
                        self.assertEqual((response.status_code, response.json()), (404, UNKNOWN))
                        self.assertNotIn("location", response.headers)
            for method, path in (("POST","/health/live"), ("POST","/health/ready"), ("GET","/mcp")):
                response = client.request(method, path)
                self.assertEqual((response.status_code,response.json()), (404,UNKNOWN))
            for path, allowed in (("/unknown",{"GET","POST"}), ("/workspaces",{"GET","POST"}), ("/health/live",{"GET"}), ("/mcp",{"POST"})):
                for method in ("PUT", "HEAD", "OPTIONS"):
                    response = client.request(method, path)
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual({value.strip() for value in response.headers["allow"].split(",")}, allowed)
                    if method != "HEAD":
                        self.assertEqual(response.json(), {"detail":"Method Not Allowed"})
            self.assertEqual(client.get("/health/live").json(), {"status":"live"})
            self.assertEqual(client.get("/health/ready").json(), {
                "status":"ready", "application":"configured", "stores":"configured",
                "runtime_interpreters":"none", "ingress_interpreters":"none", "material_provider":"disabled",
            })
        self.assertEqual(self.verifier.credentials, [])
        self.assert_no_service_work()

    def test_mcp_parse_header_auth_and_service_order_is_preserved(self):
        with TestClient(self.app) as client:
            response = client.post("/mcp", content=b"invalid JSON", headers={"Authorization":"Bearer rejected"})
            self.assertEqual((response.status_code,response.json()), (400,{"error":{"status":400,"message":"invalid JSON request body"}}))
            self.assertEqual(self.verifier.credentials, [])
            headers = {"Accept":"application/json", "MCP-Protocol-Version":"2025-06-18", "Mcp-Method":"resources/read", "Authorization":"Bearer rejected"}
            message = {"jsonrpc":"2.0", "id":"fixture", "method":"resources/read", "params":{"name":"read.run-events", "arguments":{"workspace_id":"workspace-a", "run_id":"run-a"}}}
            self.assertEqual(client.post("/mcp", json=message, headers=headers).status_code, 401)
            self.assert_no_service_work()
            headers["Authorization"] = "Bearer valid-token"
            expected = self.app.state.mcp_boundary.handle(headers=headers, message=message)
            response = client.post("/mcp", json=message, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), json.loads(json.dumps(expected.body)))
        self.assertEqual(self.verifier.credentials, [b"rejected", b"valid-token", b"valid-token"])

    def test_contract_prefix_derivation_and_rejection_before_registration(self):
        from control_plane_kit_servers_cpk_server.http_host import install_operator_http_routes
        route = self.app.state.http_boundary.composition.http_api.routes[0]
        async def endpoint(request: Request):
            return JSONResponse({"path":request.url.path})
        app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        install_operator_http_routes(app, HttpApiContract((replace(route, path_template="/future/{item}"),)), endpoint)
        with TestClient(app) as client:
            self.assertEqual(client.get("/future").json(), {"path":"/future"})
            self.assertEqual(client.post("/future/item").json(), {"path":"/future/item"})
        for path in ("/{dynamic}/item", "/__control/item", "//item"):
            app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
            prior = tuple(app.routes)
            with self.subTest(path=path), self.assertRaises(ValueError):
                install_operator_http_routes(app, HttpApiContract((route, replace(route, route_id="future", path_template=path))), endpoint)
            self.assertEqual(tuple(app.routes), prior)

        command = next(item for item in self.app.state.http_boundary.composition.http_api.routes if item.method is HttpMethod.POST)
        app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        with self.assertRaises(ValueError):
            install_operator_http_routes(app, HttpApiContract((replace(command, method=HttpMethod.PUT),)), endpoint)
        self.assertEqual(app.routes, [])

    def test_real_sdk_responses_and_framework_namespace_behavior_match_sdk_only(self):
        authority = fixture()
        reference = FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        install_control(reference, authority)
        install_control(self.app, authority)
        cases = (
            ("GET","/__control/capabilities",token(authority,static=True),200),
            ("GET","/__control/health/liveness",token(authority),200),
            ("GET","/__control/health/liveness",None,None),
            ("GET","/__control/health/liveness",token(authority,static=True),None),
            ("GET","/__control/health/readiness",token(authority,kind=NodeHealthReadKind.READINESS),None),
            ("GET","/__control/unknown",None,404),
            ("POST","/__control/health/liveness",None,405),
            ("GET","/__control/health/liveness/",None,None),
            ("GET","/%5f%5fcontrol/unknown",None,404),
            ("DELETE","/%5f%5fcontrol/unknown",None,404),
            ("GET","/__control",None,None),
        )
        with TestClient(reference,follow_redirects=False) as reference_client, TestClient(self.app,follow_redirects=False) as client:
            for method,path,credential,status in cases:
                headers = {} if credential is None else {"Authorization":f"Bearer {credential}"}
                expected = reference_client.request(method,path,headers=headers)
                actual = client.request(method,path,headers=headers)
                with self.subTest(method=method,path=path,status=status):
                    self.assertEqual((actual.status_code,actual.content), (expected.status_code,expected.content))
                    for header in ("allow","location","content-type"):
                        self.assertEqual(actual.headers.get(header),expected.headers.get(header))
                    if status is not None:
                        self.assertEqual(actual.status_code,status)
                    if status is None and path in ("/__control/health/liveness", "/__control/health/readiness"):
                        self.assertNotEqual(actual.status_code,200)
        self.assertEqual(self.verifier.credentials, [])
        self.assert_no_service_work()

    def test_sdk_still_rejects_root_wildcard_and_other_http_errors_stay_native(self):
        authority = fixture()
        collision = FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        @collision.get("/{path:path}")
        async def wildcard(path: str):
            return {}
        with self.assertRaises(ValueError):
            install_control(collision,authority)
        @self.app.get("/error")
        async def error():
            raise HTTPException(418,"fixture",headers={"x-fixture":"preserved"})
        with TestClient(self.app) as client:
            response = client.get("/error")
            self.assertEqual((response.status_code,response.json()), (418,{"detail":"fixture"}))
            self.assertEqual(response.headers["x-fixture"],"preserved")
