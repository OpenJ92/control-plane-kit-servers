"""#181 acceptance through the existing isolated public Operations driver.

This authenticated command-service fixture injects principals; it does not
exercise an external HTTP/ingress transport. It is a prepared witness, not a
completed receipt. Its caller must supply the
genuine compatible Operations factory/authority and actual acquired route plus
the real sender/gateway/SDK fixture. It never creates a successful run, returned
invocation, permission row, observation or history entry directly.
"""
from control_plane_kit_core.operations import ControlPlaneServiceRole
from control_plane_kit_core.http_verification_samples import (
    HttpVerificationSampleRequest, HttpVerificationSampleResult, http_verification_check_digest,
)
from control_plane_kit_core.verification import VerificationOutcome


async def accept_http_sample_execution(driver, *, desired_graph, approver_principal,
                                       child_node_id, original_checks, exchanges, ready_calls):
    """Execute one fresh approved deployment and join normal public history.

    exchanges contains decoded Core results captured from the real SDK reply,
    including their exact Core requests, without credentials. ready_calls records path/auth-present
    booleans from the real loopback listener. Other provider effects in the
    isolated owning fixture must be identified separately in its final receipt.
    """
    assert not exchanges and not ready_calls, "the witness must start with no sample effects"
    accepted = await driver.accept(label="signed-ready", desired_graph=desired_graph,
        destructive=False, http_verification_intent="authenticated-samples",
        approver_principal=approver_principal)
    assert accepted.plan["derivation_profile"] == "managed-http-sample-bootstrap-v1"
    observed = await driver._history_page("read.observed-state",
        path={"workspace_id": driver.workspace_id})

    # Exact command replay is already exercised by the maintained driver. A
    # second actual SDK sample or loopback ready call cannot hide behind a green
    # overall run, generic endpoint_context, or separate component receipts.
    assert len(exchanges) == len(original_checks), "original check coverage or sample count differs"
    assert all(type(result) is HttpVerificationSampleResult for result in exchanges)
    requests = tuple(result.request for result in exchanges)
    assert tuple(request.check_id for request in requests) == tuple(check.check_id for check in original_checks)
    for result, sampled, original in zip(exchanges, requests, original_checks):
        assert result.outcome is VerificationOutcome.PASSED
        assert type(sampled) is HttpVerificationSampleRequest
        assert sampled.check_digest == http_verification_check_digest(original)
        assert sampled.sample_ordinal == 1
        assert sampled.target.workspace_id.value == driver.workspace_id
        assert sampled.target.node_id.value == child_node_id
        assert sampled.run_id == accepted.claim["run_id"]
        assert sampled.authority_context.authored_graph_id == accepted.plan["desired_graph_id"]
        assert sampled.authority_context.realized_projection_id == accepted.plan["desired_realized_projection_id"]
    assert len({(request.activity_id, request.effect_id, request.outer_attempt, request.request_fingerprint)
                for request in requests}) == 1, "original checks came from different effects"
    assert len({request.request_id for request in requests}) == len(requests), "original samples reused a request ID"
    ready = [result for result in exchanges if result.request.check_id == "ready"]
    assert len(ready) == 1, "expected exactly one actual signed ready sample"
    ready_result, = ready
    request = ready_result.request
    assert ready_result.evidence.status_code == 200
    assert type(request) is HttpVerificationSampleRequest
    assert request.target.workspace_id.value == driver.workspace_id
    assert request.target.node_id.value == child_node_id
    assert request.check_id == "ready" and request.sample_ordinal == 1
    assert request.run_id == accepted.claim["run_id"]
    assert request.authority_context.authored_graph_id == accepted.plan["desired_graph_id"]
    assert request.authority_context.realized_projection_id == accepted.plan["desired_realized_projection_id"]
    assert ready_calls == [(check.path, False) for check in original_checks], \
        "original application probe recipient, order or count differs"
    assert sum(path == "/health/ready" for path, _ in ready_calls) == 1

    rows = [item for item in observed["items"]
        if item.get("payload", {}).get("http_verification", {}).get("node_id") == child_node_id
        and item["payload"]["http_verification"].get("check_id") == "ready"]
    assert len(rows) == 1, "normal observed-state API did not return one child ready result"
    row, = rows
    answer = row["payload"]["http_verification"]
    assert ((answer["run_id"], answer["activity_id"], answer["attempt"], answer["effect_id"],
            answer["node_id"], answer["check_id"], answer["http_status"])
        == (request.run_id, request.activity_id, request.outer_attempt, request.effect_id,
            child_node_id, "ready", 200)), "public result correlation differs from the actual SDK exchange"
    assert (row["status"], row["probe_outcome"]) == ("verified", "healthy")
    assert row["graph_id"] == accepted.plan["desired_graph_id"]

    runs = accepted.history["runs"]["items"]
    assert any(run["run_id"] == request.run_id for run in runs), "plan history does not contain the actual run"
    events = accepted.history["events"]["items"]
    assert any(event.get("event_id") == request.effect_id
        and event.get("activity_id") == request.activity_id and event.get("run_id") == request.run_id
        for event in events), \
        "run history does not identify the actual child check effect"
    assert accepted.execution["run_status"] == "succeeded"
    return {"plan_id": accepted.plan["plan_id"], "run_id": request.run_id,
        "activity_id": request.activity_id, "attempt": request.outer_attempt,
        "effect_id": request.effect_id, "child_node_id": child_node_id,
        "check_id": "ready", "sdk_ready_outcome": "passed", "http_status": 200,
        "public_status": row["status"], "public_probe_outcome": row["probe_outcome"],
        "sample_count": len(exchanges), "ready_sample_count": 1,
        "ready_probe_count": 1, "history_surface": "read.observed-state + read.plan-runs + read.run-events"}
