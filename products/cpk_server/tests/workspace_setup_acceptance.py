"""Actual private admission, initialization and public enrollment on owning PG."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg.conninfo import make_conninfo
from control_plane_kit_operations.workspace_permissions import WorkspacePermissionCommandService
from control_plane_kit_servers_cpk_server import bootstrap_cli as cli, bootstrap_initialization as initializer, server
from control_plane_kit_servers_cpk_server.bootstrap_workspace import workspace_helper_input_bytes
from control_plane_kit_servers_cpk_server.client import transport as client_transport
from control_plane_kit_servers_cpk_server.client.profile import ClientProfile

from cpk_http_host_fixtures import fixture as host_fixture
from dynamic_setup_fixtures import setup_inputs
from receiver_acceptance_operations import IsolatedOperationsSchema
from test_secret_provider_bootstrap import _base_environment
from workspace_initialization_fixtures import initialization_target


def workspace_setup_acceptance(database_url):
    test = TestCase()
    try:
        for fault in (None, "missing-grant", "stale-management"):
            fixture, plan, root, private, material, intent = setup_inputs(test,
                grants=fault != "missing-grant", management_revision=1 if fault == "stale-management" else 0)
            workspace = plan["input"]["installation"]["workspace_id"]
            setup_files = workspace_helper_input_bytes(plan, intent, material)
            test.assertEqual(set(setup_files), {"plan.json", "credential", "workspace-intent.json",
                "workspace-authority.json", "principals.json"})
            for name, raw in setup_files.items():
                test.assertEqual((root / name).read_bytes(), raw)
            # Separate initialization-only files never enter the public helper.
            init_root = fixture.root / "initialize-input"
            init_root.mkdir(mode=0o700)
            for name, raw in initializer.helper_input_bytes(plan, intent, material, initialization_target(plan)).items():
                fixture.private_write(init_root / name, raw)
            with IsolatedOperationsSchema(database_url, "cpk_1912_" + uuid4().hex, install_current=False) as schema:
                def connection(**options):
                    test.assertEqual(options["host"], "127.0.0.1")
                    test.assertEqual(options["port"], 5432)
                    test.assertEqual(options["options"].split().count("-csearch_path=public"), 1)
                    return psycopg.connect(database_url, autocommit=options["autocommit"],
                        connect_timeout=options["connect_timeout"], options=options["options"].replace(
                            "-csearch_path=public", "-csearch_path=" + schema.schema, 1))

                with patch.object(initializer, "connect", side_effect=connection):
                    initialized = initializer.run_workspace_initialization(input_directory=init_root,
                        progress_directory=fixture.root / "initialization-progress")
                test.assertTrue(initialized["schema_acknowledged"])
                test.assertEqual(initialized["initialization"], "matching")
                # Actual parser, verifier, startup receipt guard and current app.
                # Provider execution is excluded from this HTTP/PG component.
                environment = {**_base_environment(), "CPK_RUNTIME_INTERPRETERS": "none"}
                for name in tuple(environment):
                    if name.endswith("_DATABASE_URL"):
                        environment[name] = make_conninfo(database_url, options="-csearch_path=" + schema.schema)
                environment.update(CPK_WORKSPACE_AUTHORITY="dynamic-v1",
                    CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE=str(root / "workspace-authority.json"),
                    CPK_CONTROL_AUTH_VERIFIER="static-development",
                    CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON=(root / "principals.json").read_text())
                config = server.CpkServerBootstrapConfiguration.from_environment(environment)
                test.assertEqual(config.workspace_authority, intent.authority)
                control = host_fixture("dynamic-setup-control").config
                app = server.create_app(config, server._credential_verifier(config), control=control, clock=lambda: 150)
                progress = fixture.root / "setup-progress"
                requests = []

                def open_request(request, *, timeout):
                    parts = urlsplit(request.full_url)
                    response = client.request(request.get_method(), parts.path + ("?" + parts.query if parts.query else ""),
                        headers=dict(request.header_items()), content=request.data)
                    requests.append((request.get_method(), parts.path, response.status_code))
                    body = io.BytesIO(response.content)
                    if response.status_code >= 400:
                        raise HTTPError(request.full_url, response.status_code, "public refusal", None, body)
                    return body

                with TestClient(app) as client, \
                        patch.object(client_transport, "build_opener", return_value=SimpleNamespace(open=open_request)), \
                        patch.object(cli, "Path", side_effect=lambda path: progress if path == "/tmp/cpk-bootstrap-progress" else Path(path)), \
                        patch.object(cli.socket, "create_connection"):
                    if fault is None:
                        result = cli.public_setup(plan, root / "credential")
                        test.assertEqual(result["status"], "authenticated-local-setup")
                        test.assertEqual([entry["route"] for entry in result["commands"]], plan["setup_routes"])
                    else:
                        with test.assertRaises(fixture.api.RootBootstrapError) as caught:
                            cli.public_setup(plan, root / "credential")
                        test.assertIsNone(caught.exception.__context__)
                    saved = json.loads((progress / "progress.json").read_bytes())
                    if fault is not None:
                        expected = "command.secret-provider.register" if fault == "missing-grant" else "command.managed-runtime-access.grant"
                        test.assertEqual(saved["pending"], expected)
                        test.assertEqual(requests[-1][2], 403 if fault == "missing-grant" else 409)
                        test.assertEqual(saved["status"], "in-progress")
                        test.assertIn("command.workspace-permission.grant", [entry["route"] for entry in saved["commands"]])
                        test.assertNotIn("command.runtime-authority-delivery.register", [entry["route"] for entry in saved["commands"]])
                        continue
                    test.assertEqual(saved["status"], "complete")
                    test.assertTrue(all(status == 200 for _, _, status in requests))
                    profile = ClientProfile("http://127.0.0.1:8080", workspace,
                        {role: root / "credential" for role in ("operator", "approver", "worker")}, root / "client")
                    transport = client_transport.PublicHttpTransport(profile)

                    def call(route, payload):
                        return transport.call(route, path_parameters={"workspace_id": workspace},
                            payload=payload, credential_role="operator")

                    grant = private["administration"]["permission_grants"][0]
                    permission = call("read.workspace-permission", {"target": grant["target"]})
                    management = private["administration"]["management_grant"]
                    query = {"runtime_id": management["runtime_id"], "authority_ref": management["authority_ref"]}
                    assignment = call("read.managed-runtime-assignment", query)
                    authority = transport.call("read.runtime-authority-detail",
                        path_parameters={"workspace_id": workspace, "authority_ref": query["authority_ref"]},
                        payload={}, credential_role="operator")["runtime_authority"]
                    test.assertEqual(assignment["registration_id"], authority["registration_id"])
                    call("command.workspace-permission.revoke", {"target": grant["target"],
                        "scopes": grant["scopes"], "expected_revision": permission["revision"], "idempotency_key": "revoke-setup-ordinary"})
                    call("command.managed-runtime-access.revoke", {**query,
                        "expected_revision": assignment["revision"], "idempotency_key": "revoke-setup-management"})
                # Normal startup may read the binding but may never initialize or enroll.
                with patch.object(initializer, "run_workspace_initialization", side_effect=AssertionError("restart initialized")), \
                        patch.object(WorkspacePermissionCommandService, "initialize", side_effect=AssertionError("restart seeded")), \
                        patch.object(cli, "public_setup", side_effect=AssertionError("restart enrolled")):
                    restarted = server.create_app(config, server._credential_verifier(config), control=control, clock=lambda: 150)
                    with TestClient(restarted) as client, \
                            patch.object(client_transport, "build_opener", return_value=SimpleNamespace(open=open_request)):
                        transport = client_transport.PublicHttpTransport(profile)
                        record = call("read.workspace-permission", {"target": grant["target"]})
                        test.assertEqual(record["scopes"], [])
                        test.assertEqual(record["revision"], permission["revision"] + 1)
                        record = call("read.managed-runtime-assignment", query)
                        test.assertEqual(record["status"], "revoked")
                        test.assertEqual(record["revision"], assignment["revision"] + 1)
                        with test.assertRaises(client_transport.ClientAuthorizationError):
                            call("read.current-graph", {})
                test.assertEqual((progress / "progress.json").read_bytes(), fixture.api.canonical(saved))
        print("dynamic root setup: private admission, actual initialization, HTTP/PG enrollment, denials and restart preservation PASS", flush=True)
    finally:
        test.doCleanups()
