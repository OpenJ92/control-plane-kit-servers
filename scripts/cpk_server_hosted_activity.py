"""Drive hosted cpk-server ACTIVITY acceptance over HTTP and MCP."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime
from control_plane_kit_core.products import (
    ProductDescriptorCodec,
    ProductInstanceConfiguration,
    instantiate_product,
)
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph, compile_topology
from control_plane_kit_core.policies import PolicyScope


WORKSPACE_ID = "cpk-hosted-activity-basic"
WORKER_ID = "hosted-worker"
AUTHORIZATION = "Bearer present"


def main() -> int:
    base_url = _required_env("CPK_HOSTED_ACTIVITY_BASE_URL").rstrip("/")
    server_container = _required_env("CPK_HOSTED_ACTIVITY_SERVER_CONTAINER")
    servers_repo = Path(_required_env("CPK_HOSTED_ACTIVITY_SERVERS_REPO"))

    _wait_ready(base_url)
    product_document = _product_document(servers_repo, "hello_server")
    graph = _single_hello_graph(product_document)

    workspace = _http(
        base_url,
        "POST",
        "/workspaces",
        {
            "workspace_id": WORKSPACE_ID,
            "name": "Hosted activity smoke",
            "actor_id": "operator-a",
            "idempotency_key": f"{WORKSPACE_ID}:workspace",
        },
    )
    current_graph_id = str(workspace["workspace"]["current_graph_id"])

    _http(
        base_url,
        "POST",
        f"/workspaces/{WORKSPACE_ID}/products/import",
        {
            "descriptor_document": json.loads(product_document.content.decode("utf-8")),
            "actor_id": "operator-a",
            "imported_at": _clock(),
            "idempotency_key": f"{WORKSPACE_ID}:import:hello",
        },
    )

    if os.environ.get("CPK_HOSTED_ACTIVITY_REGISTER_PULL_AUTHORITY") == "docker-config":
        _http(
            base_url,
            "POST",
            f"/workspaces/{WORKSPACE_ID}/image-pull-authorities",
            {
                "registry": "ghcr.io",
                "repository": "openj92/control-plane-kit-servers",
                "credential_reference": "secret://docker-config/ghcr.io",
                "actor_id": "operator-a",
                "admitted_at": _clock(),
                "idempotency_key": f"{WORKSPACE_ID}:pull-authority:ghcr",
            },
        )

    session = _http(
        base_url,
        "POST",
        f"/workspaces/{WORKSPACE_ID}/sessions",
        {
            "actor_id": "operator-a",
            "title": "Hosted hello deployment",
            "idempotency_key": f"{WORKSPACE_ID}:session",
        },
    )
    session_id = str(session["session_id"])

    desired = _http(
        base_url,
        "POST",
        f"/workspaces/{WORKSPACE_ID}/graphs/desired",
        {
            "session_id": session_id,
            "actor_id": "operator-a",
            "graph": DEFAULT_GRAPH_CODEC.encode(graph),
            "expected_desired_graph_id": None,
            "idempotency_key": f"{WORKSPACE_ID}:desired",
        },
    )
    desired_graph_id = str(desired["desired_graph_id"])

    planned = _mcp_tool(
        base_url,
        "command.deployment.plan",
        {
            "workspace_id": WORKSPACE_ID,
            "session_id": session_id,
            "actor_id": "operator-a",
            "expected_current_graph_id": current_graph_id,
            "expected_desired_graph_id": desired_graph_id,
            "idempotency_key": f"{WORKSPACE_ID}:plan",
        },
    )
    plan_id = str(planned["plan_id"])
    if not planned.get("ready_for_execution", False):
        raise RuntimeError(f"plan was not approval-ready: {planned}")

    requested = _http(
        base_url,
        "POST",
        f"/workspaces/{WORKSPACE_ID}/plans/{plan_id}/approval",
        {
            "session_id": session_id,
            "actor_id": "operator-a",
            "actor_scopes": [PolicyScope.PLAN_REQUEST.value],
            "idempotency_key": f"{WORKSPACE_ID}:approval-request",
        },
    )
    approval_id = str(requested["request_id"])

    pending = _mcp_read(
        base_url,
        "read.pending-approvals",
        {"workspace_id": WORKSPACE_ID, "limit": 10, "offset": 0},
    )
    if approval_id not in {item["request_id"] for item in pending["items"]}:
        raise RuntimeError("approval request was not visible in pending queue")

    detail = _mcp_read(
        base_url,
        "read.approval-detail",
        {"workspace_id": WORKSPACE_ID, "approval_id": approval_id},
    )
    if detail["plan"]["plan_id"] != plan_id:
        raise RuntimeError("approval detail did not expose the planned transition")

    _mcp_tool(
        base_url,
        "command.approval.decide",
        {
            "session_id": session_id,
            "request_id": approval_id,
            "actor_id": "manager-a",
            "actor_scopes": [requested["required_scope"]],
            "decision": "approved",
            "idempotency_key": f"{WORKSPACE_ID}:approval-decision",
        },
    )

    admitted = _http(
        base_url,
        "POST",
        f"/workspaces/{WORKSPACE_ID}/plans/{plan_id}/admission",
        {
            "session_id": session_id,
            "approval_request_id": approval_id,
            "actor_id": "operator-a",
            "actor_scopes": [PolicyScope.PLAN_EXECUTE.value],
            "idempotency_key": f"{WORKSPACE_ID}:admit",
            "readiness": [],
        },
    )
    request_id = str(admitted["execution_request_id"])

    claimed = _http(
        base_url,
        "POST",
        f"/workspaces/{WORKSPACE_ID}/runs/{request_id}/claim",
        {
            "worker_id": WORKER_ID,
            "actor_scopes": [PolicyScope.EXECUTION_OPERATE.value],
            "lease_expires_at": "2026-07-22T12:00:00Z",
            "idempotency_key": f"{WORKSPACE_ID}:claim",
        },
    )
    run_id = str(claimed["run_id"])

    _http(
        base_url,
        "POST",
        f"/workspaces/{WORKSPACE_ID}/runs/{run_id}/start",
        {
            "worker_id": WORKER_ID,
            "actor_scopes": [PolicyScope.EXECUTION_OPERATE.value],
            "idempotency_key": f"{WORKSPACE_ID}:start",
        },
    )

    _execute_to_completion(base_url, server_container, run_id)
    _assert_body("http://hello:8000/", "Hello, world!\n")

    advanced = _http(
        base_url,
        "POST",
        f"/workspaces/{WORKSPACE_ID}/runs/{run_id}/advance-current-graph",
        {
            "plan_id": plan_id,
            "expected_current_graph_id": current_graph_id,
            "desired_graph_id": desired_graph_id,
            "worker_id": WORKER_ID,
            "actor_scopes": [PolicyScope.EXECUTION_OPERATE.value],
            "idempotency_key": f"{WORKSPACE_ID}:advance",
        },
    )
    if advanced["to_graph_id"] != desired_graph_id:
        raise RuntimeError(f"current graph did not advance: {advanced}")

    current = _http(base_url, "GET", f"/workspaces/{WORKSPACE_ID}/graphs/current")
    if current["graph_id"] != desired_graph_id:
        raise RuntimeError(f"current graph readback mismatch: {current}")

    print("hosted cpk-server Docker activity smoke passed")
    return 0


def _execute_to_completion(base_url: str, server_container: str, run_id: str) -> None:
    for attempt in range(80):
        _sync_runtime_networks(server_container)
        result = _mcp_tool(
            base_url,
            "command.deployment.execute",
            {
                "run_id": run_id,
                "worker_id": WORKER_ID,
                "actor_scopes": [PolicyScope.EXECUTION_OPERATE.value],
                "idempotency_key": f"{WORKSPACE_ID}:execute:{attempt}",
                "max_effects": 1,
            },
        )
        _sync_runtime_networks(server_container)
        if result["coordinator_status"] == "completed":
            return
        if result["coordinator_status"] in {"failed", "unsupported", "uncertain", "blocked"}:
            timeline = _http(base_url, "GET", f"/workspaces/{WORKSPACE_ID}/activity")
            raise RuntimeError(f"execution stopped with {result}; timeline={timeline}")
    raise RuntimeError("hosted activity execution did not complete")


def _sync_runtime_networks(server_container: str) -> None:
    import docker
    from docker.errors import APIError, NotFound

    client = docker.from_env()
    controller_container = socket.gethostname()
    for network in client.networks.list():
        name = network.name
        if not name.startswith(f"cpk-net-{WORKSPACE_ID}"):
            continue
        for container in (server_container, controller_container):
            try:
                network.connect(container)
            except APIError as error:
                if "already exists" in str(error).lower():
                    continue
                raise
            except NotFound:
                continue


def _wait_ready(base_url: str) -> None:
    for _ in range(30):
        try:
            ready = _http(base_url, "GET", "/health/ready", authorize=False)
        except Exception:
            time.sleep(1)
            continue
        if ready.get("status") == "ready":
            if ready.get("runtime_interpreters") != "docker":
                raise RuntimeError(f"cpk-server did not boot with Docker runtime: {ready}")
            return
        time.sleep(1)
    raise RuntimeError("cpk-server did not become ready")


def _single_hello_graph(product_document: Any) -> DeploymentGraph:
    product = product_document.product
    block = instantiate_product(
        product,
        "hello",
        ProductInstanceConfiguration.from_contract(product.runtime_contract),
    )
    return compile_topology(
        DeploymentTopology(
            WORKSPACE_ID,
            DockerRuntime(
                runtime_id="docker",
                network_name=f"control-plane-kit-{WORKSPACE_ID}-docker",
                children=(block,),
            ),
        )
    )


def _product_document(servers_repo: Path, product_name: str) -> Any:
    return ProductDescriptorCodec().decode_document(
        (servers_repo / "products" / product_name / "product.cpk.json").read_bytes()
    )


def _mcp_tool(base_url: str, name: str, arguments: dict[str, object]) -> dict[str, Any]:
    return _mcp(base_url, "tools/call", name, arguments)


def _mcp_read(base_url: str, name: str, arguments: dict[str, object]) -> dict[str, Any]:
    return _mcp(base_url, "resources/read", name, arguments)


def _mcp(base_url: str, method: str, name: str, arguments: dict[str, object]) -> dict[str, Any]:
    response = _http(
        base_url,
        "POST",
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": f"{name}:1",
            "method": method,
            "params": {"name": name, "arguments": arguments},
        },
        extra_headers={
            "Accept": "application/json",
            "MCP-Protocol-Version": "2025-06-18",
            "Mcp-Method": method,
        },
    )
    if "error" in response:
        raise RuntimeError(f"MCP {name} failed: {response}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"MCP {name} returned non-object result: {response}")
    return result


def _http(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
    *,
    authorize: bool = True,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if authorize:
        headers["Authorization"] = AUTHORIZATION
    if extra_headers:
        headers.update(extra_headers)
    request = Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            data = response.read(1024 * 1024)
    except HTTPError as error:
        detail = error.read(8192).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {method} {path} failed {error.code}: {detail}") from error
    decoded = json.loads(data.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError(f"HTTP {method} {path} returned non-object JSON")
    return decoded


def _assert_body(url: str, expected: str) -> None:
    with urlopen(url, timeout=5) as response:
        body = response.read(1024).decode("utf-8")
    if body != expected:
        raise RuntimeError(f"unexpected response from {url}: {body!r}")


def _clock() -> str:
    return "2026-07-22T10:00:00Z"


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
