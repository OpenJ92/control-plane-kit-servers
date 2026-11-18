"""Public enrollment receipt correspondence; Operations owns durable transitions."""
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_operations.workspace_permissions import (
    WorkspaceAdministrationReceipt, WorkspacePermissionReceipt, WorkspacePermissionRecord,
)
from control_plane_kit_operations.managed_runtime_assignments import ManagedRuntimeAssignmentReceipt

from .bootstrap import _closed
from .bootstrap_workspace import _identity


def _fresh_receipt(result):
    _closed(result, {"receipt", "replayed"})
    if result["replayed"] is not False:
        raise ValueError("fresh enrollment returned a replay")
    return result["receipt"]


def creation_receipt(result, intent, workspace, key):
    receipt = WorkspaceAdministrationReceipt.from_descriptor(_fresh_receipt(result))
    if (receipt.installation_id != intent.installer.installation_id
            or receipt.actor != intent.installer.identity or receipt.workspace_id != workspace
            or receipt.idempotency_key != key or receipt.initialized is not True):
        raise ValueError("workspace creation differs from intent")
    return receipt


def permission_receipt(result, intent, workspace, grant):
    value = _fresh_receipt(result)
    _closed(value, {"receipt_id", "installation_id", "workspace_id", "actor", "target", "operation",
        "scopes", "resulting_scopes", "prior_revision", "revision", "idempotency_key", "occurred_at"})
    if type(value["scopes"]) is not list or type(value["resulting_scopes"]) is not list:
        raise ValueError("permission scopes are malformed")
    receipt = WorkspacePermissionReceipt(**{**value,
        "actor": _identity(value["actor"]), "target": _identity(value["target"]),
        "scopes": tuple(PolicyScope(scope) for scope in value["scopes"]),
        "resulting_scopes": tuple(PolicyScope(scope) for scope in value["resulting_scopes"])})
    if (receipt.installation_id != intent.installer.installation_id or receipt.workspace_id != workspace
            or receipt.actor != intent.installer.identity or receipt.target != _identity(grant["target"])
            or receipt.operation != "grant" or receipt.idempotency_key != grant["idempotency_key"]
            or receipt.prior_revision != grant["expected_revision"]
            or set(receipt.scopes) != {PolicyScope(scope) for scope in grant["scopes"]}
            or not set(receipt.scopes).issubset(receipt.resulting_scopes)):
        raise ValueError("permission receipt differs from intent")
    return receipt


def verify_permission_read(value, receipt):
    # Compare the owner's resulting record, without reproducing its grant algebra.
    expected = WorkspacePermissionRecord(receipt.installation_id, receipt.workspace_id,
        receipt.target, receipt.resulting_scopes, receipt.revision).descriptor()
    if value != expected or type(value.get("revision")) is not int:
        raise ValueError("permission readback differs from receipt")


def verify_runtime_registration(value, workspace, authority_ref, registration):
    if (value.get("workspace_id") != workspace or value.get("authority_ref") != authority_ref
            or value.get("registration_id") != registration or value.get("runtime_kind") != "docker"
            or value.get("status") != "active"):
        raise ValueError("runtime registration differs from management intent")


def management_receipt(result, intent, workspace, grant, registration):
    receipt = ManagedRuntimeAssignmentReceipt.from_descriptor(_fresh_receipt(result))
    assignment = receipt.resulting_assignment
    prior_revision = 0 if receipt.prior_assignment is None else receipt.prior_assignment.revision
    if (receipt.actor != intent.installer.identity or receipt.operation != "grant"
            or receipt.idempotency_key != grant["idempotency_key"] or prior_revision != grant["expected_revision"]
            or assignment.installation_id != intent.installer.installation_id or assignment.workspace_id != workspace
            or assignment.runtime_id != grant["runtime_id"] or assignment.authority_ref.reference_id != grant["authority_ref"]
            or assignment.registration_id != registration or assignment.capability_id != grant["capability_id"]):
        raise ValueError("management receipt differs from intent")
    return receipt
