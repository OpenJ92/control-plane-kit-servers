"""Preauthorized #123 acceptance scenario through the public cpk-server API."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from typing import Any, Callable
from uuid import uuid4
from urllib.parse import urlsplit

import httpx

from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime, SocketConnection
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import (
    ProductDescriptorCodec, ProductInstanceConfiguration, instantiate_product,
)
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.secrets import SecretEnvironmentDelivery, SecretReference, SecretUseIntent
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC, DeploymentGraph, compile_topology
from control_plane_kit_core.verification import HttpCheck, VerificationContract


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
AUTHORITY = "local-docker"
WORKER_ROUTES = {
    "command.run.claim", "command.run.start", "command.deployment.execute",
    "command.graph.advance-current",
}
ATTENTION_STATUSES = {"in-flight", "uncertain", "blocked", "failed", "unsupported"}


class PublicConvergenceError(RuntimeError):
    """A fixed, non-provider diagnostic; the caller must not redispatch."""

    def __init__(self, message: str = "public convergence evidence unavailable", *,
                 category: str = "validation-failed", http_status: int | None = None) -> None:
        super().__init__(message)
        self.category = category if category in {
            "validation-failed", "http-rejected", "rpc-rejected",
            "transport-unavailable", "response-invalid",
        } else "unknown"
        self.http_status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None


def _require(condition: bool) -> None:
    if not condition:
        raise PublicConvergenceError("public convergence evidence unavailable")


def _coordinate(value: Any) -> str:
    _require(isinstance(value, str) and 0 < len(value) <= 256)
    return value


def _revision(value: Any) -> int:
    _require(type(value) is int and 0 <= value < 2**63)
    return value


def _pointer(workspace: dict[str, Any], prefix: str) -> dict[str, str] | None:
    graph = workspace[f"{prefix}_graph_id"]
    if graph is None:
        _require(workspace[f"{prefix}_realized_projection_id"] is None)
        return None
    return {
        "authored_graph_id": _coordinate(graph),
        "realized_projection_id": _coordinate(workspace[f"{prefix}_realized_projection_id"]),
    }


def _graph(
    workspace_id: str, router_id: str, nodes: tuple[dict[str, str], ...],
    selected: str, documents: dict[str, Any],
    *, connector_id: str | None = None, token_reference: str | None = None,
) -> dict[str, Any]:
    if not nodes:
        return DEFAULT_GRAPH_CODEC.encode(DeploymentGraph(workspace_id))
    children = []
    for node in nodes:
        product = documents["hello_server"].product
        configuration = ProductInstanceConfiguration.from_contract(product.runtime_contract)
        configuration = replace(configuration, public_environment=tuple(
            PublicStaticEnvironmentBinding(binding.name, node["message"])
            if binding.name == "HELLO_MESSAGE" else binding
            for binding in configuration.public_environment
        ))
        children.append(instantiate_product(product, node["node_id"], configuration))
    product = documents["http_active_router"].product
    children.extend((
        instantiate_product(product, router_id, ProductInstanceConfiguration.from_contract(product.runtime_contract)),
        SocketConnection(selected, "internal", router_id, "active"),
    ))
    if connector_id is not None:
        product = documents["cloudflared_connector"].product
        children.append(instantiate_product(
            product, connector_id, ProductInstanceConfiguration.from_contract(product.runtime_contract),
        ))
    graph = compile_topology(DeploymentTopology(workspace_id, DockerRuntime(
        runtime_id="docker", network_name=f"cpk-{workspace_id}",
        authority_ref=RuntimeAuthorityReference(AUTHORITY), children=tuple(children),
    )))
    if connector_id is not None:
        connector = graph.node(connector_id)
        graph = graph.update_node(replace(connector, secret_deliveries=(
            SecretEnvironmentDelivery("TUNNEL_TOKEN", SecretReference(token_reference),
                                      SecretUseIntent.CLOUDFLARE_TUNNEL_TOKEN),
        )))
    for node in nodes:
        value = graph.node(node["node_id"])
        graph = graph.update_node(replace(value, metadata={
            **value.metadata, "display_name": node["name"], "color": node["color"],
        }))
    message = next(node["message"] for node in nodes if node["node_id"] == selected)
    router = graph.node(router_id)
    check = HttpCheck(
        check_id="root-response", provider_socket="internal", path="/",
        expected_body_sha256=sha256((message + "\n").encode()).hexdigest(),
    )
    graph = graph.update_node(replace(router, block_spec=replace(
        router.block_spec,
        verification=VerificationContract((*router.block_spec.verification.checks, check)),
    )))
    return DEFAULT_GRAPH_CODEC.encode(graph)


def _observed_response(
    items: list[dict[str, Any]], desired: dict[str, Any], graph_id: str,
    run_id: str, router_id: str, *, previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    check = next(check for check in desired["nodes"][router_id]["block_spec"]["verification"]["checks"]
                 if check["check_id"] == "root-response")
    matches = []
    for item in items:
        evidence = item.get("payload", {}).get("http_verification", {})
        if evidence.get("node_id") != router_id or evidence.get("check_id") != check["check_id"]:
            continue
        expected_graph = graph_id if previous is None else previous["graph_id"]
        expected_run = run_id if previous is None else previous["run_id"]
        if item.get("graph_id") != expected_graph or evidence.get("run_id") != expected_run:
            continue
        if item.get("status") != "verified":
            continue
        if previous is None:
            if item.get("freshness") != "fresh":
                continue
        elif (item.get("observation_id") != previous["observation_id"]
              or item.get("freshness") != "stale" or item.get("stale_reason") != "graph-changed"):
            continue
        if evidence.get("path") != check["path"] or evidence.get("http_status") not in check["expected_statuses"]:
            continue
        size = evidence.get("response_bytes")
        if type(size) is not int or not 0 <= size <= check["policy"]["maximum_evidence_bytes"]:
            continue
        if evidence.get("expected_body_sha256") != check["expected_body_sha256"] or evidence.get("body_sha256_matches") is not True:
            continue
        matches.append({
            "observation_id": _coordinate(item["observation_id"]),
            "graph_id": expected_graph, "run_id": expected_run,
            "observed_at": item["observed_at"],
            "freshness": item["freshness"], "stale_reason": item.get("stale_reason"),
            "basis": "current-run" if previous is None else "historical-unchanged-router",
            "node_id": router_id, "check_id": check["check_id"],
            "http_status": evidence["http_status"], "response_bytes": size,
            "expected_body_sha256": check["expected_body_sha256"], "body_sha256_matches": True,
        })
    _require(len(matches) == 1)
    return matches[0]


def _plan_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    # Retain public plan identity and operations, not graph/env/change payloads.
    return {
        **{key: plan[key] for key in (
            "plan_id", "session_id", "base_graph_id", "desired_graph_id",
            "base_realized_projection_id", "desired_realized_projection_id",
            "desired_graph_revision",
        )},
        "activities": [{
            "activity_id": item["activity_id"],
            "operation": item["operation"]["kind"],
            "target": {key: value for key, value in item["operation"]["target"].items()
                       if key in {"kind", "node_id", "runtime_id", "edge_id"}},
            "dependencies": item["dependencies"], "risk": item["risk"], "impact": item["impact"],
        } for item in plan["payload"]["activities"]],
    }


def run_public_graph_convergence(
    invoke: Callable[..., dict[str, Any]], *, servers_repo: Path,
    workspace_id: str, router_id: str, hello_nodes: tuple[dict[str, str], ...],
    initial_node_id: str, rewire_node_id: str, retained_node_ids: tuple[str, ...],
    authorization: str, worker_authorization: str, approver_authorization: str, capacity: int = 32,
    max_steps: int = 512, register_pull_authority: bool = False,
    connector_token_reference: str | None = None, connector_id: str = "application-ingress",
    create_workspace: bool = True, destructive_approved: bool = False,
) -> dict[str, Any]:
    """Execute the approved scenario, or one retained application submission.

    Calling this function authorizes its fixed scenario, including removals.
    The CLI additionally requires separate affirmative approval switches.
    """
    report: dict[str, Any] = {
        "schema": "cpk.public-graph-convergence.v1", "status": "attention-required",
        "workspace_id": workspace_id, "transitions": [],
    }
    phase = "admission"
    bootstrap_step = None
    deadline = time.monotonic() + 1800
    invocation = uuid4().hex
    retained_application = connector_token_reference is not None

    def call(route: str, **arguments: Any) -> dict[str, Any]:
        _require(time.monotonic() < deadline)
        value = invoke(route, {"workspace_id": workspace_id, **arguments}, authorization=(
            approver_authorization if route == "command.approval.decide" else
            worker_authorization if route in WORKER_ROUTES else authorization
        ))
        _require(isinstance(value, dict))
        return value

    def command(route: str, key: str, **arguments: Any) -> dict[str, Any]:
        return call(route, idempotency_key=f"{invocation}:{key}", **arguments)

    def page(route: str, **arguments: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor = None
        seen = set()
        for _ in range(16):
            value = call(route, limit=100, **arguments, **({"after": cursor} if cursor is not None else {}))
            batch = value["items"]
            _require(isinstance(batch, list) and len(batch) <= 100)
            items.extend(batch)
            cursor = value.get("next_cursor")
            if cursor is None:
                return items
            _require(isinstance(cursor, dict))
            cursor_key = json.dumps(cursor, sort_keys=True, separators=(",", ":"))
            _require(len(cursor_key.encode()) <= 16384 and cursor_key not in seen)
            seen.add(cursor_key)
        raise PublicConvergenceError("public history page budget exhausted")

    try:
        minimum = 1 if retained_application else 3
        _require(type(capacity) is int and minimum <= capacity <= 128)
        _require(minimum <= len(hello_nodes) <= capacity and 1 <= max_steps <= 4096)
        _require(len({authorization, worker_authorization, approver_authorization}) == 3
                 and all((authorization, worker_authorization, approver_authorization)))
        ids = [node["node_id"] for node in hello_nodes]
        _require(len(ids) == len(set(ids)) and router_id not in ids)
        for identity in [workspace_id, router_id, *ids, *([connector_id] if retained_application else [])]:
            _require(re.fullmatch(r"[a-z][a-z0-9-]{0,62}", identity) is not None)
        for node in hello_nodes:
            for field, bound in (("name", 64), ("color", 64), ("message", 512)):
                _require(isinstance(node[field], str) and 0 < len(node[field].encode()) <= bound)
        _require(initial_node_id in ids)
        if retained_application:
            _require(connector_id not in {*ids, router_id} and not register_pull_authority)
            SecretReference(connector_token_reference)
        else:
            _require(rewire_node_id in ids and initial_node_id != rewire_node_id)
            _require(0 < len(retained_node_ids) < len(ids) and len(set(retained_node_ids)) == len(retained_node_ids))
            _require(set(retained_node_ids) <= set(ids) and rewire_node_id in retained_node_ids)
        documents = {name: ProductDescriptorCodec().decode_document(
            (servers_repo / "products" / name / "product.cpk.json").read_bytes()
        ) for name in (("hello_server", "http_active_router", "cloudflared_connector")
                      if retained_application else ("hello_server", "http_active_router"))}
        initial = tuple(node for node in hello_nodes if node["node_id"] == initial_node_id)
        retained = tuple(node for node in hello_nodes if node["node_id"] in retained_node_ids)
        phases = (("application", hello_nodes, initial_node_id),) if retained_application else (
            ("initial", initial, initial_node_id), ("multi-add", hello_nodes, initial_node_id),
            ("rewire", hello_nodes, rewire_node_id), ("subset-removal", retained, rewire_node_id),
            ("no-op", retained, rewire_node_id), ("teardown", (), rewire_node_id),
        )
        desired_graphs = [_graph(workspace_id, router_id, nodes, selected, documents,
                                connector_id=connector_id if retained_application else None,
                                token_reference=connector_token_reference)
                          for _, nodes, selected in phases]

        phase = "workspace-bootstrap"
        bootstrap_step = "workspace-create"
        workspace = (command("command.workspace.create", "workspace", name=workspace_id)["workspace"]
                     if create_workspace else call("read.workspace")["workspace"])
        bootstrap_step = "workspace-current-pointer"
        _require(workspace["workspace_id"] == workspace_id and _pointer(workspace, "current") is not None)
        admitted_workspace = (
            _pointer(workspace, "current"), _pointer(workspace, "desired"), workspace["desired_graph_revision"],
        )
        if retained_application:
            # No-op preparation may persist new desired coordinates without a run.
            # Use public plan/outcome truth, not pointer equality, to admit another edit.
            desired_pointer = _pointer(workspace, "desired")
            current_pointer = _pointer(workspace, "current")
            if desired_pointer is not None:
                sessions = page("read.activity")
                _require(len(sessions) <= 64)
                matches = []
                for session in sessions:
                    for prior in page("read.session-plans", session_id=_coordinate(session["session_id"])):
                        if (prior["desired_graph_id"] == desired_pointer["authored_graph_id"]
                                and prior["desired_realized_projection_id"] == desired_pointer["realized_projection_id"]
                                and prior["desired_graph_revision"] == workspace["desired_graph_revision"]):
                            matches.append(prior)
                _require(len(matches) == 1)
                prior = call("read.plan-detail", plan_id=_coordinate(matches[0]["plan_id"]))["plan"]
                _require(prior["status"] == "planned")
                prior_runs = page("read.plan-runs", plan_id=prior["plan_id"])
                if prior["payload"]["activities"]:
                    _require(desired_pointer == current_pointer and bool(prior_runs)
                             and all(run["status"] == "succeeded" for run in prior_runs))
                else:
                    _require(not prior_runs and prior["base_graph_id"] == current_pointer["authored_graph_id"]
                             and prior["base_realized_projection_id"] == current_pointer["realized_projection_id"])
                    # An empty public plan establishes no changes; descriptors
                    # are redacted projections, not round-trip intent values.
                    for route, pointer in (("read.desired-graph", desired_pointer),
                                           ("read.current-graph", current_pointer)):
                        observed = call(route)
                        _require(observed["graph_id"] == pointer["authored_graph_id"]
                                 and observed["realized_projection_id"] == pointer["realized_projection_id"])
        for name, document in documents.items():
            bootstrap_step = {"hello_server": "hello-product-import", "http_active_router": "router-product-import",
                              "cloudflared_connector": "connector-product-import"}[name]
            command("command.product.import", f"import:{name}",
                    descriptor_document=json.loads(document.content), imported_at=_clock())
        if retained_application and create_workspace:
            bootstrap_step = "secret-provider-registration"
            provider = command("command.secret-provider.register", "secret-provider",
                               provider_id="persistent-demo-secrets", provider_kind="control-plane-kit-secrets",
                               display_name="Persistent application custody", endpoint_reference="persistent-demo-secrets",
                               credential_reference="secret://bootstrap/provider/demo-client-token",
                               allowed_reference_prefixes=[connector_token_reference],
                               allowed_intents=["cloudflare.tunnel-token"], admitted_at=_clock(), metadata={})
            command("command.secret-reference.register", "tunnel-reference",
                    reference=connector_token_reference, provider_registration_id=_coordinate(provider["registration_id"]),
                    allowed_intents=["cloudflare.tunnel-token"], admitted_at=_clock(), metadata={})
        bootstrap_step = "runtime-authority-register"
        command("command.runtime-authority.register", "authority",
                authority_ref=AUTHORITY, runtime_kind="docker",
                authority={"kind": "local-docker-socket"}, admitted_at=_clock())
        bootstrap_step = "runtime-authority-delivery-register"
        command("command.runtime-authority-delivery.register", "delivery", delivery={
            "authority_ref": {"reference_id": AUTHORITY},
            "delivery_kind": "local-docker-socket-mount", "secret_references": [],
        }, admitted_at=_clock())
        if register_pull_authority:
            for name, document in documents.items():
                bootstrap_step = {"hello_server": "hello-pull-authority-register", "http_active_router": "router-pull-authority-register"}[name]
                image = json.loads(document.content)["product"]["image"]
                _require(image["registry"] == "ghcr.io")
                command("command.image-pull-authority.register", f"pull-authority:{name}",
                        registry=image["registry"], repository=image["repository"],
                        credential_reference="secret://docker-config/ghcr.io", admitted_at=_clock())

        previous_response = None
        previous_desired = None
        for (phase, _, _), desired in zip(phases, desired_graphs):
            workspace = call("read.workspace")["workspace"]
            if retained_application:
                _require((_pointer(workspace, "current"), _pointer(workspace, "desired"),
                          workspace["desired_graph_revision"]) == admitted_workspace)
            current = _pointer(workspace, "current")
            _require(current is not None)
            report["last_observed_graph_id"] = current["authored_graph_id"]
            prepared = command("command.deployment.prepare", f"{phase}:prepare",
                               desired_graph=desired, expected_current=current,
                               expected_desired=_pointer(workspace, "desired"),
                               expected_desired_graph_revision=_revision(workspace["desired_graph_revision"]),
                               title=f"Public convergence {phase}")
            row: dict[str, Any] = {"phase": phase, "plan_id": _coordinate(prepared["plan_id"]),
                                   "status": "attention-required"}
            report["transitions"].append(row)
            row["preparation"] = {key: prepared[key] for key in (
                "status", "plan_id", "approval_request_id") if key in prepared}
            plan = call("read.plan-detail", plan_id=row["plan_id"])["plan"]
            row["plan"] = _plan_evidence(plan)
            if prepared["status"] == "no-changes":
                _require(phase == "no-op" or retained_application)
                row["status"] = "no-changes"
                continue
            if prepared["status"] != "approval-required":
                report["phase"] = phase
                return report
            _require(phase != "no-op")
            plan_id = row["plan_id"]
            approval_id = _coordinate(prepared["approval_request_id"])
            approval = call("read.approval-detail", approval_id=approval_id)["approval"]
            row["approval"] = {key: approval[key] for key in (
                "request_id", "session_id", "required_scope", "destructive", "state")}
            session_id = _coordinate(plan["session_id"])
            _require(plan["plan_id"] == plan_id and approval["request_id"] == approval_id)
            _require(approval["session_id"] == session_id and approval["state"] == "pending")
            _require(plan["base_graph_id"] == current["authored_graph_id"])
            _require(plan["base_realized_projection_id"] == current["realized_projection_id"])
            _require(approval["required_scope"] in {"plan:approve", "plan:approve-destructive"})
            if retained_application and (approval["destructive"] or approval["required_scope"] == "plan:approve-destructive"):
                _require(destructive_approved)
            if phase in {"subset-removal", "teardown"}:
                _require(approval["destructive"] is True and approval["required_scope"] == "plan:approve-destructive")
            decided = command("command.approval.decide", f"{phase}:approve",
                              approval_id=approval_id, session_id=session_id, decision="approved")
            _require(decided["state"] == "approved")
            approved = call("read.approval-detail", approval_id=approval_id)["approval"]
            _require(approved["state"] == "approved" and approved["request_id"] == approval_id)
            _require(approved["decision"]["actor_id"] != approved["requested_by"])
            row["approval"].update(
                state=approved["state"], requested_by=approved["requested_by"],
                decision={key: approved["decision"][key] for key in (
                    "decision_id", "actor_id", "decision", "scope", "decided_at")},
            )
            row["outcomes"] = []
            admitted = command("command.deployment.admit", f"{phase}:admit",
                               plan_id=plan_id, session_id=session_id,
                               approval_request_id=approval_id, readiness=[])
            claimed = command("command.run.claim", f"{phase}:claim",
                              run_id=_coordinate(admitted["execution_request_id"]), lease_duration_seconds=1800)
            run_id = _coordinate(claimed["run_id"])
            generation = _revision(claimed["claim_generation"])
            _require(generation > 0)
            row.update(run_id=run_id, approval_request_id=approval_id)
            started = command("command.run.start", f"{phase}:start", run_id=run_id, claim_generation=generation)
            _require(started["run_status"] == "running")
            for ordinal in range(max_steps):
                executed = command("command.deployment.execute", f"{phase}:execute:{ordinal}",
                                   run_id=run_id, claim_generation=generation, max_effects=1)
                _require(executed["run_id"] == run_id)
                row["outcomes"].append({key: executed[key] for key in (
                    "run_id", "run_status", "coordinator_status", "effects_attempted", "activity_id")})
                status = executed["coordinator_status"]
                if status == "completed":
                    _require(executed["run_status"] == "succeeded")
                    break
                if status != "progressed":
                    report.update(phase=phase, coordinator_status=(status if status in ATTENTION_STATUSES else "unknown"))
                    return report
            else:
                report.update(phase=phase, coordinator_status="execution-budget-exhausted")
                return report
            graph_id = _coordinate(plan["desired_graph_id"])
            projection_id = _coordinate(plan["desired_realized_projection_id"])
            revision = _revision(plan["desired_graph_revision"])
            advanced = command("command.graph.advance-current", f"{phase}:advance",
                               run_id=run_id, plan_id=plan_id, claim_generation=generation,
                               expected_current_graph_id=current["authored_graph_id"],
                               expected_current_realized_projection_id=current["realized_projection_id"],
                               desired_graph_id=graph_id, desired_realized_projection_id=projection_id,
                               expected_desired_graph_revision=revision)
            _require(advanced["to_graph_id"] == graph_id and advanced["to_realized_projection_id"] == projection_id)
            _require(advanced["desired_graph_revision"] == revision)
            row["advancement"] = {key: advanced[key] for key in (
                "to_graph_id", "to_realized_projection_id", "desired_graph_revision")}
            observed_current = call("read.current-graph")
            _require(observed_current["graph_id"] == graph_id)
            _require(observed_current["realized_projection_id"] == projection_id)
            report["last_observed_graph_id"] = graph_id
            row["graph_id"] = graph_id
            runs = page("read.plan-runs", plan_id=plan_id)
            _require(any(item["run_id"] == run_id and item["status"] == "succeeded" for item in runs))
            events = page("read.run-events", run_id=run_id)
            _require(bool(events))
            row["runs"] = [{key: item[key] for key in ("run_id", "status")} for item in runs]
            # Event payloads may contain provider details; retain the public lifecycle,
            # coordinates and ordinal, paired with bounded command outcomes above.
            row["events"] = [{key: item[key] for key in (
                "event_id", "run_id", "ordinal", "event_type", "occurred_at", "activity_id")}
                for item in events]
            if desired["nodes"]:
                router_activities = [item for item in row["plan"]["activities"]
                                     if item["target"] == {"kind": "node", "node_id": router_id}]
                checks_router = any(item["operation"] == "wait-for-healthy" for item in router_activities)
                if not checks_router and retained_application:
                    row["response"] = {"basis": "not-observed", "freshness": "unknown"}
                elif not checks_router:
                    _require(not router_activities and previous_response is not None and previous_desired is not None)
                    _require(desired["nodes"][router_id] == previous_desired["nodes"][router_id])
                    _require(desired["edges"] == previous_desired["edges"])
                    _require(phase not in {"initial", "rewire"})
                if checks_router or not retained_application:
                    row["response"] = _observed_response(
                        page("read.observed-state"), desired, graph_id, run_id, router_id,
                        previous=None if checks_router else previous_response,
                    )
                previous_response = row["response"]
                previous_desired = desired
            else:
                _require(not observed_current["graph_descriptor"]["nodes"])
            row.update(status="converged", graph_id=graph_id, event_count=len(events))
        report["status"] = "converged"
        report["final_graph_id"] = report["last_observed_graph_id"]
    except Exception as error:
        # A failed/ambiguous call is never repeated or converted into success.
        report.update(status="attention-required", phase=phase)
        if phase == "workspace-bootstrap":
            report["bootstrap_step"] = bootstrap_step
        report["failure"] = {
            "category": error.category if isinstance(error, PublicConvergenceError) else "unknown",
            "http_status": error.http_status if isinstance(error, PublicConvergenceError) else None,
        }
    return report


def _clock() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class McpTransport:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def invoke(self, route: str, arguments: dict[str, Any], *, authorization: str) -> dict[str, Any]:
        method = "resources/read" if route.startswith("read.") else "tools/call"
        payload = {"jsonrpc": "2.0", "id": uuid4().hex, "method": method,
                   "params": {"name": route, "arguments": arguments}}
        try:
            with self.client.stream("POST", "/mcp", json=payload, headers={
                "Authorization": authorization, "MCP-Protocol-Version": "2025-06-18", "Mcp-Method": method,
            }) as response:
                if response.status_code != 200:
                    raise PublicConvergenceError(category="http-rejected", http_status=response.status_code)
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise PublicConvergenceError(category="response-invalid", http_status=200)
                    body.extend(chunk)
        except httpx.TransportError:
            raise PublicConvergenceError(category="transport-unavailable") from None
        try:
            decoded = json.loads(body)
        except (ValueError, UnicodeError):
            raise PublicConvergenceError(category="response-invalid", http_status=200) from None
        if not isinstance(decoded, dict):
            raise PublicConvergenceError(category="response-invalid", http_status=200)
        if "error" in decoded:
            raise PublicConvergenceError(category="rpc-rejected", http_status=200)
        if not isinstance(decoded.get("result"), dict):
            raise PublicConvergenceError(category="response-invalid", http_status=200)
        return decoded["result"]


def write_bootstrap(directory: Path, *, workspaces: tuple[str, ...] | None = None,
                    application_workspace: str | None = None, provider_endpoint: str | None = None) -> None:
    """Generate private local bootstrap files in a fresh invocation directory."""
    workspace = os.environ["CPK_PUBLIC_CONVERGENCE_WORKSPACE"]
    workspaces = workspaces or (workspace,)
    operator, approver, worker, password = (secrets.token_hex(32) for _ in range(4))
    grants = ["hub:instance:create", "hub:instance:read", "instance:workspace:read",
              "instance:workspace:edit", "plan:request",
              "plan:execute", "runtime-authority:register", "runtime-authority:use",
              "runtime-authority-delivery:register"]
    principals = [
        {"credential": operator, "subject_id": "convergence-operator", "kind": "operator", "workspace_grants": {
            name: grants + (["secret-provider:register", "secret-provider:read", "secret-provider:use"]
                            if name == application_workspace else []) for name in workspaces}},
        {"credential": approver, "subject_id": "convergence-approver", "kind": "operator", "workspace_grants": {
            name: ["plan:approve", "plan:approve-destructive"] for name in workspaces}},
        {"credential": worker, "subject_id": "convergence-worker", "kind": "worker", "workspace_grants": {
            name: ["execution:operate"] + (["secret-provider:use"] if name == application_workspace else [])
            for name in workspaces}},
    ]
    database = f"postgresql://cpk:{password}@cpk-postgres:5432/cpk"
    server = {"CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON": json.dumps(principals, separators=(",", ":")),
              **{f"CPK_{name}_DATABASE_URL": database for name in (
                  "WORKPLACE", "ACTIVITY_HISTORY", "OBSERVER_STATE", "GRAPH_TOPOLOGY")}}
    controller = {"CPK_PUBLIC_CONVERGENCE_OPERATOR": operator, "CPK_PUBLIC_CONVERGENCE_APPROVER": approver,
                  "CPK_PUBLIC_CONVERGENCE_WORKER": worker}
    postgres = {"POSTGRES_DB": "cpk", "POSTGRES_USER": "cpk", "POSTGRES_PASSWORD": password}
    if provider_endpoint is not None:
        server.update({
            "CPK_MATERIAL_PROVIDER_ROUTES_JSON": json.dumps({"persistent-demo-secrets": provider_endpoint}),
            "CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON": json.dumps({
                "secret://bootstrap/provider/demo-client-token": "/run/secrets/cpk-provider/client-token",
            }),
        })
    for name, values in (("server.env", server), ("controller.env", controller), ("postgres.env", postgres)):
        descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write("".join(f"{key}={value}\n" for key, value in values.items()))


def write_persistent_bootstrap(directory: Path) -> None:
    """Fresh installation only; existing provider authority is copied, never minted."""
    workspace = os.environ["CPK_PUBLIC_CONVERGENCE_WORKSPACE"]
    workspaces = tuple(os.environ["CPK_DEMO_WORKSPACES"].split(","))
    _require(1 <= len(workspaces) <= 16 and len(set(workspaces)) == len(workspaces))
    _require(workspace in workspaces)
    for value in workspaces:
        _require(re.fullmatch(r"[a-z][a-z0-9-]{0,62}", value) is not None)
    endpoint = os.environ["CPK_DEMO_PROVIDER_URL"]
    parsed = urlsplit(endpoint)
    _require(parsed.scheme in {"http", "https"} and parsed.hostname is not None
             and parsed.username is None and parsed.password is None and not parsed.query
             and not parsed.fragment and len(endpoint) <= 1024 and "\n" not in endpoint)
    reference = SecretReference(os.environ["CPK_DEMO_TOKEN_REFERENCE"])
    provider_credential = Path("/provider-credential").read_bytes()
    _require(0 < len(provider_credential) <= 16384)
    write_bootstrap(directory, workspaces=workspaces, application_workspace=workspace, provider_endpoint=endpoint)
    for name, content in (
        ("ownership.id", uuid4().hex.encode() + b"\n"),
        ("provider-client-token", provider_credential),
        ("application.json", json.dumps({"workspace_id": workspace, "token_reference": reference.reference_id},
                                       sort_keys=True).encode()),
    ):
        descriptor = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            if name == "provider-client-token":
                # Only the pinned non-root server reads this individual bind mount.
                os.fchown(output.fileno(), 10001, 10001)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve-transitions", action="store_true", required=True)
    parser.add_argument("--approve-destructive", action="store_true")
    parser.add_argument("--retained-application", type=Path)
    parser.add_argument("--create-workspace", action="store_true")
    parser.add_argument("--active-node", type=int, default=1)
    parser.add_argument("--nodes", type=int, default=4)
    parser.add_argument("--capacity", type=int, default=32)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    retained = args.retained_application is not None
    _require((1 if retained else 3) <= args.nodes <= args.capacity <= 128)
    _require(retained or args.approve_destructive)
    _require(1 <= args.active_node <= args.nodes)
    workspace = os.environ["CPK_PUBLIC_CONVERGENCE_WORKSPACE"]
    application = None
    if retained:
        raw = args.retained_application.read_bytes()
        _require(len(raw) <= 4096)
        application = json.loads(raw)
        _require(set(application) == {"workspace_id", "token_reference"} and application["workspace_id"] == workspace)
        SecretReference(application["token_reference"])
    colors = ("red", "green", "blue", "gold", "violet", "teal")
    nodes = tuple({"node_id": f"hello-{i + 1}" if retained else f"hello-{uuid4().hex[:12]}", "name": f"service-{i + 1}",
                   "color": colors[i % len(colors)],
                   "message": f"Hello from service-{i + 1} in {colors[i % len(colors)]}"}
                  for i in range(args.nodes))
    with httpx.Client(base_url=os.environ.get("CPK_PUBLIC_CONVERGENCE_URL", "http://cpk-server:8080"),
                      timeout=120, trust_env=False, follow_redirects=False) as client:
        ready = False
        for attempt in range(30):
            try:
                with client.stream("GET", "/health/ready", timeout=5) as response:
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        _require(len(body) + len(chunk) <= 8192)
                        body.extend(chunk)
                    if response.status_code == 200:
                        health = json.loads(body)
                        ready = health.get("status") == "ready"
                        if ready:
                            _require(health.get("runtime_interpreters") == "docker")
            except httpx.TransportError:
                pass
            if ready:
                break
            if attempt < 29:
                time.sleep(1)
        _require(ready)
        report = run_public_graph_convergence(
            McpTransport(client).invoke, servers_repo=Path("/source"), workspace_id=workspace,
            router_id="application-router" if retained else f"router-{uuid4().hex[:12]}", hello_nodes=nodes,
            initial_node_id=nodes[args.active_node - 1 if retained else 0]["node_id"], rewire_node_id=nodes[-1]["node_id"],
            retained_node_ids=tuple(node["node_id"] for node in nodes[1::2]) if args.nodes % 2 == 0
            else tuple(node["node_id"] for node in nodes[::2]),
            authorization="Bearer " + os.environ["CPK_PUBLIC_CONVERGENCE_OPERATOR"],
            worker_authorization="Bearer " + os.environ["CPK_PUBLIC_CONVERGENCE_WORKER"],
            approver_authorization="Bearer " + os.environ["CPK_PUBLIC_CONVERGENCE_APPROVER"],
            capacity=args.capacity, register_pull_authority=os.environ.get("CPK_PUBLIC_CONVERGENCE_PULL_AUTHORITY") == "1",
            connector_token_reference=application["token_reference"] if retained else None,
            create_workspace=args.create_workspace if retained else True,
            destructive_approved=args.approve_destructive,
        )
    rendered = json.dumps(report, sort_keys=True, separators=(",", ":"))
    _require(len(rendered.encode()) <= MAX_REPORT_BYTES)
    # A fresh owned evidence directory is mounted separately from bootstrap.
    # Any write/flush failure leaves the controller nonzero and history retained.
    descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(rendered + "\n")
        output.flush()
        os.fsync(output.fileno())
    directory = os.open(args.report.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    print(json.dumps({"status": report["status"], "transitions": len(report["transitions"])}))
    return 0 if report["status"] == "converged" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print('{"status":"attention-required","phase":"bootstrap-or-transport"}')
        sys.exit(1)
