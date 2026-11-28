"""Post-deployment enrollment through the normal child MCP listener."""
from contextlib import asynccontextmanager
import json

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def verify_enrollment(base_url, owner_token, member_token, owner, member):
    workspace = {"workspace_id": "first-hello"}
    target = {**workspace, "target": member}
    creation = {**workspace, "name": "First Hello workspace", "idempotency_key": "owner-create-hello"}
    grant = {**target, "scopes": ["instance:workspace:read"], "expected_revision": 0,
             "idempotency_key": "owner-grant-read"}

    @asynccontextmanager
    async def connect(token):
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + token}) as http:
            async with Client(streamable_http_client(base_url + "/mcp", http_client=http)) as client:
                yield client

    async def call(client, tool, arguments, *, error=None):
        reply = await client.call_tool(tool, arguments)
        if error is not None:
            assert reply.is_error and reply.structured_content["error"]["status"] == error, tool
        else:
            assert not reply.is_error, tool
        return reply.structured_content

    async with connect(member_token) as ordinary:
        await call(ordinary, "create_workspace_as_administrator", creation, error=403)
    async with connect(owner_token) as admin:
        created = (await call(admin, "create_workspace_as_administrator", creation))["receipt"]
        assert created["initialized"] and created["workspace_id"] == workspace["workspace_id"]
        assert created["actor"] == owner and created["idempotency_key"] == creation["idempotency_key"]
        assert (await call(admin, "list_workspace_permissions", workspace))["items"] == []
    async with connect(member_token) as ordinary:
        await call(ordinary, "get_workspace", workspace, error=403)
        await call(ordinary, "grant_workspace_permissions", grant, error=403)
    async with connect(owner_token) as admin:
        receipt = (await call(admin, "grant_workspace_permissions", grant))["receipt"]
        assert receipt["actor"] == owner and receipt["target"] == member and receipt["revision"] == 1
        await call(admin, "grant_workspace_permissions", {**grant, "idempotency_key": "stale"}, error=409)
        record = await call(admin, "inspect_workspace_permission", target)
        assert record["scopes"] == grant["scopes"] and record["revision"] == receipt["revision"]
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + owner_token}) as http:
            response = await http.get(base_url + "/workspaces/first-hello/permissions/inspect",
                                      params={"target": json.dumps(member)})
            assert response.status_code == 200 and response.json() == record
    async with connect(member_token) as fresh:
        state = (await call(fresh, "get_workspace", workspace))["workspace"]
        assert state["workspace_id"] == workspace["workspace_id"]
        assert state["current_graph_id"] == created["observed_current_graph_id"]
        await call(fresh, "get_workspace", {"workspace_id": "foreign-workspace"}, error=403)
    async with connect(owner_token) as admin:
        revoked = (await call(admin, "revoke_workspace_permissions",
            {**grant, "expected_revision": record["revision"], "idempotency_key": "owner-revoke-read"}))["receipt"]
        assert revoked["resulting_scopes"] == [] and revoked["revision"] == 2
        query = {**target, "limit": 1}
        page = await call(admin, "list_workspace_permission_history", query)
        assert page["next_cursor"]
        rest = await call(admin, "list_workspace_permission_history", {**query, "after": page["next_cursor"]})
        assert rest["next_cursor"] is None
        assert {r["receipt_id"] for r in page["items"] + rest["items"]} == {receipt["receipt_id"], revoked["receipt_id"]}
    async with connect(member_token) as fresh:
        await call(fresh, "get_workspace", workspace, error=403)
