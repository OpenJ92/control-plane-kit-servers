"""Reviewed private setup input and actual owner response values, without stores."""
import importlib

from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_operations.workspace_permissions import (
    WorkspaceAdministrationReceipt, WorkspaceAdministrationResult,
    WorkspacePermissionReceipt, WorkspacePermissionResult, WorkspacePermissionRecord,
)
from control_plane_kit_operations.managed_runtime_assignments import (
    ManagedRuntimeAssignment, ManagedRuntimeAssignmentReceipt, ManagedRuntimeAssignmentResult,
    ManagedRuntimeAssignmentStatus, managed_runtime_assignment_id,
)
from test_dynamic_root_bootstrap import DynamicRootBootstrapTests, TOKEN


def setup_inputs(test, *, management=True, grants=True):
    fixture = DynamicRootBootstrapTests()
    fixture.setUp()
    test.addCleanup(fixture.doCleanups)
    document, policy, private = fixture.inputs(multiple=True)
    installation = document["installation"]
    # This fixture describes intent, not the permission transition algorithm.
    private["administration"]["permission_grants"] = ([{
        "target": private["installer"], "scopes": [
            "instance:workspace:read", "instance:workspace:edit",
            "runtime-authority:register", "runtime-authority:read",
            "runtime-authority-delivery:register", "runtime-authority-delivery:read",
            "secret-provider:register", "secret-provider:read"],
        "expected_revision": 0, "idempotency_key": "private-setup-grant-key"}] if grants else [])
    private["administration"]["management_grant"] = ({
        "runtime_id": installation["installation_id"] + "-docker",
        "authority_ref": installation["runtime_authority"], "capability_id": "installed-management",
        "expected_revision": 0, "idempotency_key": "private-management-key",
        "registration_from": "command.runtime-authority.register"} if management else None)
    document["setup"]["administration"] = {"permission_grant_count": int(grants), "management_grant": management}
    fixture.bind_intent(document, policy, private)
    plan = fixture.plan(document)
    index, _ = fixture.material(plan, policy, private)
    runtime = importlib.import_module("control_plane_kit_servers_cpk_server.bootstrap_runtime")
    material, intent = runtime._material(plan, index)
    root = fixture.root / "setup-input"
    root.mkdir(mode=0o700)
    private = {**private, "plan_digest": plan["digest"],
        "policy": {**private["policy"], "file": "workspace-authority.json"}}
    values = {"plan.json": fixture.api.canonical(plan), "workspace-intent.json": fixture.api.canonical(private),
        "workspace-authority.json": policy, "credential": TOKEN.encode(),
        "principals.json": material[installation["control_auth"]["principals_document"]].encode()}
    for name, raw in values.items():
        fixture.private_write(root / name, raw)
    return fixture, plan, root, private, material, intent


def owner_responses(plan, private, registration="authority-observed"):
    installation = plan["input"]["installation"]
    identity = private["installer"]
    actor = PrincipalIdentity(identity["issuer"], identity["subject_id"], PrincipalKind(identity["kind"]))
    timestamp = "2026-10-28T14:00:00Z"
    installed, workspace = installation["installation_id"], installation["workspace_id"]
    administration = private["administration"]
    created = WorkspaceAdministrationResult(WorkspaceAdministrationReceipt(installed, actor, workspace,
        administration["workspace_creation_idempotency_key"], True, "current-observed", timestamp)).descriptor()
    grant = administration["permission_grants"][0]
    scopes = tuple(PolicyScope(value) for value in grant["scopes"])
    granted = WorkspacePermissionResult(WorkspacePermissionReceipt("grant-receipt-observed", installed,
        workspace, actor, actor, "grant", scopes, scopes, 0, 1, grant["idempotency_key"], timestamp)).descriptor()
    permission = WorkspacePermissionRecord(installed, workspace, actor, scopes, 1).descriptor()
    management = administration["management_grant"]
    assignment = None
    managed = None
    if management is not None:
        authority = RuntimeAuthorityReference(management["authority_ref"])
        assignment = ManagedRuntimeAssignment(managed_runtime_assignment_id(installed, workspace,
            management["runtime_id"], authority), installed, workspace, management["runtime_id"], authority,
            registration, management["capability_id"], ManagedRuntimeAssignmentStatus.ACTIVE, 1)
        managed = ManagedRuntimeAssignmentResult(ManagedRuntimeAssignmentReceipt("management-receipt-observed",
            actor, "grant", None, assignment, management["idempotency_key"], timestamp)).descriptor()
    return created, granted, permission, managed, None if assignment is None else assignment.descriptor()
