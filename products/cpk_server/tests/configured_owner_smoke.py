"""Normal product process, disposable database, and the child's actual signed ready check."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
from subprocess import Popen
import sys
import time
from unittest import TestCase
from urllib.error import URLError
from urllib.request import urlopen

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
import psycopg
from psycopg.conninfo import make_conninfo

from cpk_http_host_fixtures import fixture
from http_sample_fixture import SampleAuthority, verify_sample, write_public
from mcp_workspace_enrollment import verify_enrollment
from control_plane_kit_operations.postgres import install_schema
from control_plane_kit_servers_cpk_server import control_configuration as receiver
from control_plane_kit_servers_cpk_server.configured_owner import install_or_verify_owner
from control_plane_kit_servers_cpk_server.workspace_authority_configuration import decode_workspace_authority_configuration

BASE = "http://127.0.0.1:8080"
DATABASE = "postgresql://cpk:cpk@cpk-postgres:5432/cpk451"
OWNER = {"issuer": "urn:control-plane-kit:static-development", "subject_id": "fixture-owner", "kind": "operator"}
MEMBER = {**OWNER, "subject_id": "fixture-member"}
POLICY = {"schema": "cpk-server.workspace-authority.v1", "installation_id": "smoke-child",
          "administrators": [OWNER], "known_identities": [OWNER, MEMBER], "capabilities": []}


def environment(token):
    roles = ("WORKPLACE", "ACTIVITY_HISTORY", "OBSERVER_STATE", "GRAPH_TOPOLOGY")
    credentials = [{"subject_id": identity["subject_id"], "kind": "operator", "credential": value,
                    "workspace_grants": {}} for identity, value in ((OWNER, token), (MEMBER, "test-member"))]
    return {**os.environ, **{f"CPK_{role}_DATABASE_URL": DATABASE for role in roles},
            "CPK_PORT": "8080", "CPK_SERVER_MODE": "execution-capable", "CPK_RUNTIME_INTERPRETERS": "none",
            "CPK_CONTROL_AUTH_VERIFIER": "static-development", "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON": json.dumps(credentials),
            "CPK_WORKSPACE_AUTHORITY": "configured-owner-v1", "CPK_WORKSPACE_AUTHORITY_CONFIGURATION_FILE": "/tmp/policy.json",
            "CPK_HTTP_VERIFICATION_SAMPLES_CONFIGURATION_FILE": receiver.HTTP_SAMPLE_SLOT.target_path}


@contextmanager
def listening(environment):
    process = Popen([sys.executable, "-m", "control_plane_kit_servers_cpk_server.server"], env=environment)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("child exited before opening its listener")
            try:
                with urlopen(BASE + "/health/live", timeout=1) as response:
                    if response.status == 200:
                        break
            except URLError:
                time.sleep(0.1)
        else:
            raise RuntimeError("child listener timed out")
        yield
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)


async def observe_mcp(owner_token, rejected_token):
    async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + owner_token}) as http:
        permission_url = BASE + "/workspaces/not-enrolled/permissions"
        page = await http.get(permission_url)
        assert page.status_code == 200 and page.json()["items"] == []
        member = await http.get(permission_url, headers={"Authorization": "Bearer test-member"})
        assert member.status_code == 403

        async with Client(streamable_http_client(BASE + "/mcp", http_client=http)) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert "get_workspace" in names and "inspect_workspace_permission" in names
            admin_read = await client.call_tool("inspect_workspace_permission",
                {"workspace_id": "not-enrolled", "target": MEMBER})
            assert admin_read.is_error and admin_read.structured_content["error"]["status"] == 404
            result = await client.call_tool("get_workspace", {"workspace_id": "not-enrolled"})
            assert result.is_error and result.structured_content["error"]["status"] == 403
        denied = await http.post(BASE + "/mcp", headers={"Authorization": "Bearer " + rejected_token,
            "Accept": "application/json, text/event-stream"}, json={"jsonrpc": "2.0", "id": 1,
            "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "owner-test", "version": "1"}}})
        assert denied.status_code == 401


def binding(*, enrolled=False):
    with psycopg.connect(DATABASE) as connection:
        expected_rows = 1 if enrolled else 0
        assert connection.execute("SELECT count(*) FROM cpk_workspaces").fetchone() == (expected_rows,)
        assert connection.execute("SELECT count(*) FROM cpk_workspace_permissions").fetchone() == (expected_rows,)
        (receipt,), = connection.execute("SELECT receipt FROM cpk_workspace_permission_installation").fetchall()
        assert receipt["installation_id"] == POLICY["installation_id"] and receipt["actor"] == OWNER
        return receipt


def check_retained_and_concurrent():
    with psycopg.connect(DATABASE, autocommit=True) as connection:
        connection.execute("CREATE SCHEMA unbound")
        connection.execute("CREATE SCHEMA simultaneous")
    policy = decode_workspace_authority_configuration(json.dumps(POLICY).encode()).administration_policy

    def bind(schema):
        install_or_verify_owner(make_conninfo(DATABASE, options="-csearch_path=" + schema), policy,
            clock=lambda: "2026-11-27T00:00:00Z", id_factory=lambda: "unused")
    unbound = make_conninfo(DATABASE, options="-csearch_path=unbound")
    with psycopg.connect(unbound) as connection:
        install_schema(connection)
    from control_plane_kit_operations.workspace_permissions import WorkspacePermissionNotFound
    with TestCase().assertRaises(WorkspacePermissionNotFound):
        bind("unbound")
    with psycopg.connect(unbound) as connection:
        assert connection.execute("SELECT count(*) FROM cpk_workspace_permission_installation").fetchone() == (0,)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(bind, ["simultaneous", "simultaneous"]))
    with psycopg.connect(DATABASE) as connection:
        assert connection.execute("SELECT count(*) FROM simultaneous.cpk_workspace_permission_installation").fetchone() == (1,)


def main():
    policy_path = Path("/tmp/policy.json")
    policy_path.write_text(json.dumps(POLICY))
    policy_path.chmod(0o600)
    control = fixture("owner-smoke").config
    control_artifact = receiver.cpk_control_configuration_artifact(control)
    write_public(Path(receiver.CONTROL_PATH), control_artifact.content.encode())
    contract = receiver.cpk_source_runtime_contract(receiver.CpkSourceVariant.CPK, control_artifact)
    sample = SampleAuthority(control, contract)
    artifact = receiver.cpk_http_sample_configuration_artifact(control, sample.configuration)
    write_public(Path(artifact.target_path), artifact.content.encode())
    receipt = None
    for current, rejected in (("owner-first", "invalid"), ("owner-rotated", "owner-first")):
        with listening(environment(current)):
            verify_sample(BASE, sample, sample.check)
            asyncio.run(observe_mcp(current, rejected))
            observed = binding()
            if receipt is not None:
                assert receipt == observed
                asyncio.run(verify_enrollment(BASE, current, "test-member", OWNER, MEMBER))
            receipt = observed

    # A credentialed member cannot take over the same installation by changing the policy file.
    policy_path.write_text(json.dumps({**POLICY, "administrators": [MEMBER]}))
    refused = Popen([sys.executable, "-m", "control_plane_kit_servers_cpk_server.server"],
                    env=environment("owner-rotated"))
    try:
        assert refused.wait(timeout=20) == 2
    finally:
        if refused.poll() is None:
            refused.kill()
            refused.wait(timeout=5)
    assert binding(enrolled=True) == receipt
    check_retained_and_concurrent()
    print("configured owner: signed ready, fresh native MCP, rotation, restart, ownership and namespace checks passed")


if __name__ == "__main__":
    main()
