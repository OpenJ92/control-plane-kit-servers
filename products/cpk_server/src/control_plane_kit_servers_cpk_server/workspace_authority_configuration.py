"""Installer-only policy input; no credentials, workspace grants or store effects."""
import json
import os
import stat

from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
from control_plane_kit_operations.managed_runtime_assignments import (
    ManagedRuntimeCapability, ManagedRuntimeCapabilityPolicy,
)
from control_plane_kit_operations.workspace_permissions import WorkspaceAdministrationPolicy

from .operations_application import WorkspaceAuthorityConfiguration


_INVALID = "workspace authority process configuration is invalid"
_MAX_BYTES = 1_048_576
_INPUT_ERRORS = (ValueError, TypeError, AttributeError, KeyError, OverflowError, RecursionError)


def _object(value, keys):
    if type(value) is not dict or value.keys() != keys:
        raise ValueError
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError


def _identities(values):
    if type(values) is not list or not 1 <= len(values) <= 1024:
        raise ValueError
    result = []
    for value in values:
        _object(value, {"issuer", "subject_id", "kind"})
        result.append(PrincipalIdentity(value["issuer"], value["subject_id"], PrincipalKind(value["kind"])))
    return tuple(result)


def decode_workspace_authority_configuration(raw: bytes) -> WorkspaceAuthorityConfiguration:
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_BYTES:
            raise ValueError
        value = _object(json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant),
            {"schema", "installation_id", "administrators", "known_identities", "capabilities"})
        if value["schema"] != "cpk-server.workspace-authority.v1":
            raise ValueError
        capabilities = value["capabilities"]
        if type(capabilities) is not list or len(capabilities) > 64:
            raise ValueError
        return WorkspaceAuthorityConfiguration(
            WorkspaceAdministrationPolicy(value["installation_id"], _identities(value["administrators"]),
                _identities(value["known_identities"])),
            ManagedRuntimeCapabilityPolicy(value["installation_id"],
                tuple(ManagedRuntimeCapability(capability) for capability in capabilities)))
    except _INPUT_ERRORS:
        failure = ValueError(_INVALID)
    raise failure


def read_workspace_authority_configuration(path: str) -> WorkspaceAuthorityConfiguration:
    """Read once from a bounded regular file; parent directories are installer-trusted."""
    try:
        if (type(path) is not str or not 1 <= len(path.encode("utf-8")) <= 4096
                or not os.path.isabs(path)
                or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in path)):
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= _MAX_BYTES:
                raise ValueError
            content = bytearray()
            while len(content) <= _MAX_BYTES:
                chunk = os.read(descriptor, min(65_536, _MAX_BYTES + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
            return decode_workspace_authority_configuration(bytes(content))
        finally:
            os.close(descriptor)
    except (*_INPUT_ERRORS, OSError):
        failure = ValueError(_INVALID)
    raise failure
