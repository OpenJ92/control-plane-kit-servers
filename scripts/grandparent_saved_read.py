"""One fixed four-GET verification, with no Docker socket or switch entrypoint."""
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys

from grandparent_cpk_cutover import (
    CURRENT, DESIRED, DRAFT, WORKSPACE, Hold, ReadFailure, READ_ROUTES,
    SavedReads, VerifiedProfile, canonical, require,
)

RUN = "cpk399-gparent-saved-read-20261114-01"
BASELINE_SHA = "f3b0f8a2321e521a989c3a8d84e51c7431b1c8e3056c0e4a0a08c7e05a702e2a"
CURRENT_PROJECTION = "projection-da2f787b2e3ef72074946d4baa37c9c99c4b4d9c4734f613256cee0a94b26fe9"
DESIRED_PROJECTION = "projection-73df8846ec2c913b8a3f79072e28fca5f7aec2c89514359c6399f79bad88f2ca"


def summarize(snapshot, baseline):
    """Compare owner-redacted public values; never expose a graph/response body."""
    from control_plane_kit_operations.read_services.workspace_graph import _redact_graph_descriptor
    workspace, desired, revision, attempts = json.loads(snapshot)
    expected = json.loads(canonical(_redact_graph_descriptor(baseline)))
    require(type(baseline) is dict and baseline["name"] == WORKSPACE
            and type(baseline["nodes"]) is dict and len(baseline["nodes"]) == 8, "baseline-shape")
    for suffix, graph in (("desired", desired["graph_descriptor"]), ("revision", revision["graph_descriptor"])):
        if canonical(graph) != canonical(expected):
            raise ReadFailure(READ_ROUTES[suffix], "baseline-mismatch", phase="compare")
    SavedReads.check("workspace", lambda: canonical(workspace["desired_graph"]) == canonical(desired)
        and workspace["workspace"]["desired_realized_projection_id"] == desired["realized_projection_id"] == DESIRED_PROJECTION
        and desired["pointer"] == "desired" and desired["authored_graph_id"] == DESIRED
        and workspace["workspace"]["current_realized_projection_id"] == CURRENT_PROJECTION
        and workspace["current_graph"]["assigned"] is True
        and workspace["current_graph"]["pointer"] == "current"
        and workspace["current_graph"]["graph_id"] == workspace["current_graph"]["authored_graph_id"] == CURRENT
        and workspace["current_graph"]["realized_projection_id"] == CURRENT_PROJECTION)
    return dict(workspace_id=WORKSPACE, current_graph_id=CURRENT, desired_graph_id=DESIRED,
        desired_generation=1, draft_id=DRAFT, revision=1, named_coordinates_verified=True,
        desired_projection_consistent=True, desired_realized_projection_id=DESIRED_PROJECTION,
        current_realized_projection_id=CURRENT_PROJECTION, public_graph=dict(node_count=8,
            node_names=sorted(baseline["nodes"]), desired_matches_owner_redacted_baseline=True,
            revision_matches_owner_redacted_baseline=True, private_authored_bytes_compared=False),
        attempts=dict(limit=10, returned=len(attempts["items"]),
            next_cursor_present=attempts["next_cursor"] is not None, coverage="first-page-only",
            page_exhausted_observed=attempts["next_cursor"] is None),
        canonical_snapshot_sha256=hashlib.sha256(snapshot).hexdigest())


def main():
    reader = None
    stage = "invocation"
    result = dict(schema="cpk399.saved-read-verification.v1", run=RUN, status="HOLD",
        retry=False, service_mutation=False, switch_attempted=False, graph_mutation=False,
        client_attached=False, completed_reads=0)
    try:
        require(len(sys.argv) == 3 and sys.argv[1] == "--verify-saved-read-only"
                and re.fullmatch(r"[0-9a-f]{64}", sys.argv[2]), "invocation")
        stage = "reader-owner"
        require((os.getuid(), os.getgid()) == (501, 20), "reader-owner")
        stage = "plan-read"
        raw_plan = Path("/proposal/verification.json").read_bytes()
        stage = "plan-digest"
        require(hashlib.sha256(raw_plan).hexdigest() == sys.argv[2], "plan-digest")
        stage = "plan-decode"
        plan = json.loads(raw_plan)
        stage = "authority"
        require(plan["schema"] == "cpk399.read-only-approval.v1" and plan["run"] == RUN
                and plan["read_once_approved"] is True
                and plan["endpoint"] == "http://127.0.0.1:18163"
                and plan["routes"] == list(READ_ROUTES.values()), "authority")
        stage = "reader-source-read"
        raw_reader = Path(__file__).read_bytes()
        stage = "reader-source-check"
        require(plan["reader_sha256"] == hashlib.sha256(raw_reader).hexdigest(), "authority")
        stage = "shared-source-read"
        raw_shared = Path("/grandparent_cpk_cutover.py").read_bytes()
        stage = "shared-source-check"
        require(plan["shared_reader_sha256"] == hashlib.sha256(raw_shared).hexdigest(), "authority")
        stage = "proxy-environment"
        require(not any(v for k, v in os.environ.items() if k.lower() in
                    {"http_proxy", "https_proxy", "all_proxy"}), "proxy-environment")
        stage = "baseline-read"
        raw_baseline = Path("/public/desired.json").read_bytes()
        stage = "baseline-digest"
        require(hashlib.sha256(raw_baseline).hexdigest() == BASELINE_SHA, "baseline-digest")
        stage = "baseline-decode"
        baseline = json.loads(raw_baseline)
        logging.disable(logging.CRITICAL)
        stage = "credential-metadata"
        reader = SavedReads(Path("/credentials/human.bearer"))
        stage = "credential-load"
        credential = reader.owner_credential()
        # Custody and the explicit approved reference select the human bearer;
        # the fixed public API authenticates it. No extra identity HTTP call or
        # private principal-document read is performed in this read-only batch.
        stage = "profile-pin"
        reader.profile = VerifiedProfile(reader.owner_profile, credential)
        stage = "saved-reads"
        snapshot = reader.saved()
        stage = "snapshot-compare"
        result.update(summarize(snapshot, baseline), status="verified")
        stage = "verified"
        status = 0
    except ReadFailure as error:
        result["read_failure"] = error.record()
        stage = error.stage
        status = 1
    except BaseException as error:
        result["reason"] = "read-verification-unverified"
        if reader is not None and stage == "saved-reads":
            stage = reader.stage
        # Never serialize exception text, filenames, response bodies, or locals.
        category = "unexpected"
        if isinstance(error, PermissionError):
            category = "permission-denied"
        elif isinstance(error, FileNotFoundError):
            category = "file-unavailable"
        elif isinstance(error, json.JSONDecodeError):
            category = "invalid-json"
        elif isinstance(error, Hold):
            category = "check-refused"
        elif type(error).__name__ == "ClientConfigurationError":
            category = "credential-configuration"
        result["failure_category"] = category
        status = 1
    result["stage"] = stage
    if reader is not None:
        result["completed_reads"] = len(reader.completed_routes)
    print(canonical(result).decode())
    return status


if __name__ == "__main__":
    sys.exit(main())
