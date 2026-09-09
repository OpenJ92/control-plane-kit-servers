"""The narrow public API steps used by the complete-child acceptance recipe.

Run in the ordinary Docker controller with explicit ClientProfiles. This module
has no Docker/SQL/provider access and never approves a plan implicitly. The
owning fixture supplies the external root, initial custody and controlled parent
restart under its separately reviewed action plan.
"""

import json
from hashlib import sha256
from pathlib import Path

from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime
from control_plane_kit_core.topology import DeploymentGraph, GraphDescriptorCodec, compile_topology
from control_plane_kit_servers_cpk_server.client import SavedDesiredRevision
from control_plane_kit_servers_cpk_server.client.installation import (
    ChildInstallationHold, child_installation_document, initialize_child_workspace,
)


def _read(client, route, **coordinates):
    return client.transport.call(route,
        path_parameters={"workspace_id": client.profile.workspace_id, **coordinates},
        payload={}, credential_role="operator")


def parent_tracking(client, operation_ref):
    """Reconnect-safe authoritative coordinates, independent of process memory."""
    status = client.status(operation_ref)
    if (status.status != "converged" or status.execution != "succeeded"
            or status.advancement != "advanced" or not status.plan_id or not status.run_id):
        raise ChildInstallationHold("parent operation is not verified converged")
    detail = _read(client, "read.plan-detail", plan_id=status.plan_id).get("plan", {})
    current = _read(client, "read.current-graph")
    workspace = _read(client, "read.workspace").get("workspace", {})
    if (workspace.get("workspace_id") != client.profile.workspace_id
            or detail.get("plan_id") != status.plan_id
            or current.get("graph_id") != detail.get("desired_graph_id")
            or current.get("realized_projection_id") != detail.get("desired_realized_projection_id")
            or workspace.get("current_graph_id") != current.get("graph_id")
            or workspace.get("current_realized_projection_id") != current.get("realized_projection_id")):
        raise ChildInstallationHold("parent history does not match realized child deployment")
    # The existing report owns run/history pagination and correlation, not this
    # recipe. Persist it as evidence without treating it as a fresh child probe.
    report = client.report([operation_ref]).descriptor()
    rows = report.get("operations", [])
    if len(rows) != 1 or rows[0].get("operation_ref") != operation_ref:
        raise ChildInstallationHold("parent history report does not identify the operation")
    history = rows[0]
    if (any(history.get(name, {}).get("state") != "observed" for name in ("plan", "session", "approval", "runs"))
            or history.get("association", {}).get("state") not in {"matched", "not-applicable"}):
        raise ChildInstallationHold("parent history association is not verified")
    runs = history["runs"].get("data", [])
    run = next((item for item in runs if item.get("run_id") == status.run_id), None)
    if (run is None or run.get("status") != "succeeded"
            or run.get("events", {}).get("state") not in {"observed", "truncated"}
            or not run["events"].get("data")):
        raise ChildInstallationHold("parent successful run history is unavailable")
    return {"operation_ref": operation_ref, "workspace_id": client.profile.workspace_id,
            "plan_id": status.plan_id, "run_id": status.run_id,
            "current_graph_id": current["graph_id"],
            "current_realized_projection_id": current["realized_projection_id"],
            "history": history, "report": report}


def initialize_after_parent(installation, *, parent, prepared, child, setup, state_directory):
    """Require observed parent convergence before any child initialization call."""
    expected = child_installation_document(installation, child_workspace_id=child.profile.workspace_id)
    if (parent.profile.workspace_id != expected["parent_workspace_id"]
            or prepared.workspace_id != parent.profile.workspace_id or not prepared.plan_id):
        raise ChildInstallationHold("parent preparation does not identify this installation")
    tracking = parent_tracking(parent, prepared.operation_ref)
    if tracking["plan_id"] != prepared.plan_id:
        raise ChildInstallationHold("parent operation plan differs from reviewed preparation")
    # Public graph reads redact protected bindings. Use the existing client's
    # validated original-input digest and returned plan coordinates to bind the
    # exact composed graph; node names alone cannot establish identity.
    invocation = parent.journal.read(prepared.operation_ref)
    expected_bytes = json.dumps(expected["graph"], sort_keys=True,
                                separators=(",", ":"), allow_nan=False).encode()
    coordinates = invocation.get("coordinates", {})
    target = invocation.get("target", {})
    if (invocation.get("desired", {}).get("sha256") != sha256(expected_bytes).hexdigest()
            or target.get("workspace_id") != parent.profile.workspace_id
            or target.get("endpoint_sha256") != parent.profile.target_digest
            or coordinates.get("plan_id") != prepared.plan_id
            or coordinates.get("desired_graph_id") != tracking["current_graph_id"]
            or coordinates.get("desired_realized_projection_id") != tracking["current_realized_projection_id"]):
        raise ChildInstallationHold("parent operation is not bound to the exact intended child graph")
    initialized = initialize_child_workspace(installation, child=child, setup=setup,
                                             state_directory=state_directory)
    return {"parent": tracking, "child": initialized}


def child_runtime_graph(installation, child_workspace_id):
    """One explicit child Docker runtime; its plan must be non-noop to earn proof."""
    return compile_topology(DeploymentTopology(child_workspace_id,
        DockerRuntime(runtime_id=f"{installation.installation_id}-proof",
                      network_name=f"cpk-{installation.installation_id}-proof",
                      authority_ref=installation.runtime_access.authority_ref, children=())))


def prepare_saved_empty(client, *, graph_path: Path):
    """Save/select/read EMPTY desired state before preparing that saved revision.

    The caller separately inspects and supplies exact destructive approval to
    TopologyClient.apply. No runtime effect or retained deletion occurs here.
    """
    empty = GraphDescriptorCodec().encode(DeploymentGraph(client.profile.workspace_id))
    # This is a new invocation-owned, secret-free graph artifact. Refuse reuse.
    with graph_path.open("x", encoding="utf-8") as stream:
        json.dump(empty, stream, sort_keys=True, separators=(",", ":"))
    saved = client.draft_save(graph_path, title="Remove child installation").descriptor()
    if saved.get("status") != "recorded" or saved.get("workspace_id") != client.profile.workspace_id:
        raise ChildInstallationHold("empty desired revision was not saved")
    revision = saved.get("revision", {})
    source = SavedDesiredRevision(revision.get("draft_id"), revision.get("revision"))
    selected = client.draft_select(source.draft_id, source.revision).descriptor()
    if selected.get("status") != "recorded" or selected.get("revision") != revision:
        raise ChildInstallationHold("empty desired revision was not selected")
    detail = _read(client, "read.desired-topology-draft-revision",
                   draft_id=source.draft_id, revision=str(source.revision))
    desired = _read(client, "read.desired-graph")
    overview = _read(client, "read.operator-overview")
    draft = overview.get("graphs", {}).get("desired", {}).get("draft", {})
    if (detail.get("workspace_id") != client.profile.workspace_id
            or detail.get("draft_id") != source.draft_id or detail.get("revision") != source.revision
            or detail.get("graph_id") != revision.get("graph_id") or detail.get("graph_descriptor") != empty
            or desired.get("graph_id") != revision.get("graph_id") or desired.get("graph_descriptor") != empty
            or draft.get("state") != "selected" or draft.get("selected") != revision or draft.get("head") != revision):
        raise ChildInstallationHold("selected latest desired revision is not the saved empty graph")
    planned = client.plan(source, title="Deploy selected empty revision")
    return {"revision": revision, "prepared": planned}


def verify_empty_convergence(client, operation_ref, *, revision):
    """API convergence proves graph removal; it never claims retained data wiped."""
    tracking = parent_tracking(client, operation_ref)
    expected = GraphDescriptorCodec().encode(DeploymentGraph(client.profile.workspace_id))
    current = _read(client, "read.current-graph")
    desired = _read(client, "read.desired-graph")
    if (current.get("graph_id") != revision["graph_id"] or current.get("graph_descriptor") != expected
            or desired.get("graph_id") != revision["graph_id"] or desired.get("graph_descriptor") != expected):
        raise ChildInstallationHold("empty desired revision has not converged")
    return {"tracking": tracking, "compute_graph": "empty", "retained_data": "requires-explicit-accounting"}
