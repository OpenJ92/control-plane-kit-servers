"""Native MCP wire shapes for the existing workspace administration owner."""
from control_plane_kit_core.identity import PrincipalKind
from control_plane_kit_core.policies import PolicyScope


def _object(required, **optional):
    return {"type": "object", "properties": {**required, **optional},
            "required": list(required), "additionalProperties": False}


def _page(item, cursor):
    return _object({"items": {"type": "array", "maxItems": 10, "items": item},
                    "next_cursor": {"anyOf": [cursor, {"type": "null"}]}})


def _result(receipt):
    return _object({"receipt": receipt, "replayed": {"type": "boolean"}})


# Core supplies the identity and scope vocabulary. The Operations decoder and
# services enforce exact UTF-8 byte limits, tenant binding, fences and policy.
_text = {"type": "string", "minLength": 1, "maxLength": 512}
_key = {**_text, "maxLength": 200}
_revision = {"type": "integer", "minimum": 0, "maximum": 9223372036854775806}
_identity = _object({"issuer": _text, "subject_id": _text,
                     "kind": {"enum": [kind.value for kind in PrincipalKind]}})
_scopes = {"type": "array", "uniqueItems": True, "maxItems": len(PolicyScope),
           "items": {"enum": [scope.value for scope in PolicyScope]}}
_workspace = {"workspace_id": _text}
_target = {**_workspace, "target": _identity}
_coordinates = {"installation_id": _text, **_workspace}
_attribution = {**_coordinates, "actor": _identity, "idempotency_key": _key,
                "occurred_at": {"type": "string", "maxLength": 27}}
_limit = {"type": "integer", "minimum": 1, "maximum": 10}

_list_cursor = _object({"kind": {"const": "workspace-permissions"}, **_coordinates, "after": _identity})
_history_cursor = _object({"kind": {"const": "workspace-permission-history"}, **_coordinates,
                           "target": _identity, "after_revision": {**_revision, "minimum": 1}})
_permission = _object({**_coordinates, "target": _identity, "scopes": _scopes, "revision": _revision})
_change = _object({**_target, "scopes": {**_scopes, "minItems": 1},
                   "expected_revision": _revision, "idempotency_key": _key})
_change_receipt = _object({**_attribution, "receipt_id": _text, "target": _identity,
                           "operation": {"enum": ["grant", "revoke"]}, "scopes": {**_scopes, "minItems": 1},
                           "resulting_scopes": _scopes, "prior_revision": _revision,
                           "revision": {**_revision, "minimum": 1}})
_create = _object({**_workspace, "name": _text, "idempotency_key": _key}, metadata={"type": "object",
                  "description": "Optional public workspace metadata within the owner's command size limit."})
_create_receipt = _object({**_attribution, "initialized": {"type": "boolean"}, "observed_current_graph_id": _text})

WORKSPACE_ADMINISTRATION_SCHEMAS = {
    "command.workspace-administration.create": (_create, _result(_create_receipt)),
    "command.workspace-permission.grant": (_change, _result(_change_receipt)),
    "command.workspace-permission.revoke": (_change, _result(_change_receipt)),
    "read.workspace-permission": (_object(_target), _permission),
    "read.workspace-permissions": (_object(_workspace, limit=_limit, after=_list_cursor),
                                   _page(_permission, _list_cursor)),
    "read.workspace-permission-history": (_object(_target, limit=_limit, after=_history_cursor),
                                         _page(_change_receipt, _history_cursor)),
}
