"""One #399 SDK2.3 discovery + workspace read; human file only, no setup."""
import asyncio
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import stat

IDENTITY = "cpk399-sibling-20261114-01"
ENDPOINT = "http://127.0.0.1:18263/mcp"
CREDENTIAL = Path("/credentials/human.bearer")
TOOLS = {"get_workspace", "get_desired_graph", "get_desired_topology_draft_revision",
         "list_desired_topology_draft_revision_attempts"}


async def read_workspace():
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    from control_plane_kit_servers_cpk_server.client.profile import ClientProfile
    if (os.getuid(), os.getgid()) != (501, 20) or importlib.metadata.version("mcp") != "2.3.0":
        raise ValueError
    if any(value for name, value in os.environ.items() if name.lower() in {"http_proxy", "https_proxy", "all_proxy"}):
        raise ValueError
    info = CREDENTIAL.lstat()
    if not stat.S_ISREG(info.st_mode) or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_size) != (501, 20, 0o400, 64):
        raise ValueError
    profile = ClientProfile("http://127.0.0.1:18263", IDENTITY,
        {role: CREDENTIAL for role in ("operator", "approver", "worker")}, Path("/tmp/unused-client-state"))
    human = profile.credential("operator").decode("ascii")
    async with httpx2.AsyncClient(timeout=10, trust_env=False, follow_redirects=False,
            headers={"Authorization": "Bearer " + human}) as http:
        async with Client(streamable_http_client(ENDPOINT, http_client=http), mode="auto") as client:
            tools = (await client.list_tools()).tools
            if {tool.name for tool in tools} != TOOLS or not all(tool.annotations.read_only_hint for tool in tools):
                raise ValueError
            result = await client.call_tool("get_workspace", {"workspace_id": IDENTITY})
            if result.is_error or result.structured_content["workspace"]["workspace_id"] != IDENTITY:
                raise ValueError
            # Persist no response body, credential, private metadata or history.
            return dict(status="verified", client="mcp.Client", mcp_version="2.3.0",
                endpoint=ENDPOINT, workspace_id=IDENTITY, protocol=client.protocol_version,
                discovery=sorted(TOOLS), tool_calls=["get_workspace"], credential_role="fresh-human",
                credential_values_recorded=False, graph_writes=0, codex_client_configured=False)


def main():
    logging.disable(logging.CRITICAL)
    try:
        result = asyncio.run(asyncio.wait_for(read_workspace(), timeout=45))
    except BaseException:
        print('{"status":"HOLD","stage":"mcp-workspace-verification","credential_values_recorded":false}')
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
