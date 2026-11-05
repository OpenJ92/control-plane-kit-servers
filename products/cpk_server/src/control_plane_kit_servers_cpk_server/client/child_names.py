"""Retained account-local naming intent, independent of deployment operations."""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID, uuid4
from urllib.parse import urlsplit

from control_plane_kit_core.public_ingress import (
    IngressAuthorityReference, PublicIngressLifecycle,
)
from .profile import normalize_endpoint
from .frontend import _canonical_origin


_SCHEMA = "cpk.child-names.v1"
_LIMIT = 16384
_STATE_PARTS = (".local", "state", "cpk", "child-installations")
_ROLES = {"api": "api", "website": "web", "management": "management"}
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


class ChildNamingError(ValueError):
    """Naming state needs investigation; no deployment was requested."""


def _require(condition):
    if not condition:
        raise ChildNamingError("child naming intent is unavailable or conflicting")


def _identity(value):
    _require(type(value) is str and _IDENTITY.fullmatch(value) is not None)


def _parent_origin(value):
    try:
        _require(normalize_endpoint(value) == value)
        parsed = urlsplit(value)
        if parsed.scheme == "https":
            return _canonical_origin(value)
        # The profile owner already restricts plaintext HTTP to exact loopback
        # hosts. Close its base-URL shape to one origin spelling here.
        _require(not parsed.path and parsed.port != 80)
        return value
    except ValueError:
        failure = ChildNamingError("child parent origin is invalid")
    raise failure from None


@dataclass(frozen=True, slots=True)
class ChildIngressNameBinding:
    role: str
    ingress_id: str
    authority_ref: str
    lifecycle: PublicIngressLifecycle

    def __post_init__(self):
        _require(type(self.role) is str and self.role in _ROLES)
        _identity(self.ingress_id)
        _identity(self.authority_ref)
        _require(type(self.lifecycle) is PublicIngressLifecycle)
        IngressAuthorityReference(self.authority_ref)


@dataclass(frozen=True, slots=True)
class ChildNameBinding:
    parent_endpoint: str
    parent_installation_id: str
    parent_workspace_id: str
    child_installation_id: str
    zone_name: str
    ingresses: tuple[ChildIngressNameBinding, ...]

    def __post_init__(self):
        _parent_origin(self.parent_endpoint)
        for value in (self.parent_installation_id, self.parent_workspace_id,
                self.child_installation_id):
            _identity(value)
        _require(type(self.zone_name) is str and 1 <= len(self.zone_name) <= 206)
        _require(all(_LABEL.fullmatch(label) for label in self.zone_name.split(".")))
        _require(type(self.ingresses) is tuple and len(self.ingresses) == 3)
        _require(all(type(item) is ChildIngressNameBinding for item in self.ingresses))
        for item in self.ingresses:
            item.__post_init__()
        _require({item.role for item in self.ingresses} == set(_ROLES))
        _require(len({item.ingress_id for item in self.ingresses}) == 3)
        object.__setattr__(self, "ingresses", tuple(sorted(self.ingresses, key=lambda item: item.role)))


@dataclass(frozen=True, slots=True)
class AssignedChildIngress:
    role: str
    hostname: str


@dataclass(frozen=True, slots=True)
class ChildNameAssignment:
    binding: ChildNameBinding
    public_id: str
    ingresses: tuple[AssignedChildIngress, ...]


def _assignment_root():
    # This lifetime belongs to the OS account, independent of profile/cwd/output.
    return Path.home().joinpath(*_STATE_PARTS)


def _binding_descriptor(binding):
    return {
        "parent_endpoint": binding.parent_endpoint,
        "parent_installation_id": binding.parent_installation_id,
        "parent_workspace_id": binding.parent_workspace_id,
        "child_installation_id": binding.child_installation_id,
        "zone_name": binding.zone_name,
        "ingresses": [{"role": item.role, "ingress_id": item.ingress_id,
            "authority_ref": item.authority_ref, "lifecycle": item.lifecycle.value}
            for item in binding.ingresses],
    }


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _assignment(binding, public_id):
    _require(type(public_id) is str)
    parsed = UUID(public_id)
    _require(parsed.version == 4 and parsed.hex == public_id)
    return ChildNameAssignment(binding, public_id, tuple(
        AssignedChildIngress(item.role, _ROLES[item.role] + "-" + public_id + "." + binding.zone_name)
        for item in binding.ingresses))


def _descriptor(assignment):
    return {"schema": _SCHEMA, "binding": _binding_descriptor(assignment.binding),
        "public_id": assignment.public_id,
        "ingresses": [{"role": item.role, "hostname": item.hostname} for item in assignment.ingresses]}


def _present(path):
    # lstat also treats a dangling symlink as an occupied, unsafe path.
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _directory(create):
    root = _assignment_root()
    _require(isinstance(root, Path) and root.is_absolute())
    for component in (root, *root.parents):
        _require(not component.is_symlink())
    anchor = root.parents[len(_STATE_PARTS) - 1]
    _require(root.relative_to(anchor).parts == _STATE_PARTS)
    information = anchor.lstat()
    _require(stat.S_ISDIR(information.st_mode) and information.st_uid == os.getuid()
        and stat.S_IMODE(information.st_mode) & 0o022 == 0)
    chain = (root, *root.parents[:len(_STATE_PARTS) - 1])
    for component in reversed(chain):
        if create:
            component.mkdir(mode=0o700, exist_ok=True)
        information = component.lstat()
        _require(stat.S_ISDIR(information.st_mode) and information.st_uid == os.getuid()
            and stat.S_IMODE(information.st_mode) & 0o022 == 0)
        # Visibility may come from a creator that has not synced this entry.
        # Every successful caller establishes all links below the account anchor.
        _sync_directory(component.parent)
    information = root.lstat()
    _require(stat.S_ISDIR(information.st_mode) and information.st_uid == os.getuid()
        and stat.S_IMODE(information.st_mode) == 0o700)
    return root


def _paths(root, binding):
    key = {name: value for name, value in _binding_descriptor(binding).items()
        if name in ("parent_endpoint", "parent_installation_id", "parent_workspace_id", "child_installation_id")}
    name = sha256(_encode(key)).hexdigest()
    return root / (name + ".json"), root / (name + ".pending")


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value)
        value[key] = item
    return value


def _read(path, binding):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        information = os.fstat(stream.fileno())
        _require(stat.S_ISREG(information.st_mode) and information.st_uid == os.getuid()
            and stat.S_IMODE(information.st_mode) == 0o600 and 0 < information.st_size <= _LIMIT)
        raw = stream.read(_LIMIT + 1)
    _require(0 < len(raw) <= _LIMIT)
    value = json.loads(raw, object_pairs_hook=_unique_object)
    _require(type(value) is dict and set(value) == {"schema", "binding", "public_id", "ingresses"})
    assignment = _assignment(binding, value["public_id"])
    _require(value == _descriptor(assignment) and raw == _encode(value))
    return assignment


def _sync_directory(root):
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish(root, final, pending, binding):
    # Exclusive pending creation arbitrates the first writer. A loser never owns
    # this path and must leave it in place, including after a caller interruption.
    descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        identity = os.fstat(stream.fileno())
        _require(stat.S_IMODE(identity.st_mode) == 0o600)
        # The previous creator may have finished between our optimistic read and
        # acquiring pending. Reuse its final without allocating another label.
        if _present(final):
            observed = _read(final, binding)
            pending_identity = pending.lstat()
            _require((pending_identity.st_dev, pending_identity.st_ino) == (identity.st_dev, identity.st_ino))
            pending.unlink()
            _sync_directory(root)
            return observed
        assignment = _assignment(binding, uuid4().hex)
        raw = _encode(_descriptor(assignment))
        _require(len(raw) <= _LIMIT)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(root)
    os.link(pending, final, follow_symlinks=False)
    _sync_directory(root)
    observed = _read(final, binding)
    _require(observed == assignment)
    pending_identity = pending.lstat()
    final_identity = final.lstat()
    _require((pending_identity.st_dev, pending_identity.st_ino)
        == (final_identity.st_dev, final_identity.st_ino)
        == (identity.st_dev, identity.st_ino))
    pending.unlink()
    _sync_directory(root)
    return observed


def _load_or_create(binding, *, create):
    _require(type(binding) is ChildNameBinding)
    binding.__post_init__()
    root = _directory(create)
    final, pending = _paths(root, binding)
    _require(not _present(pending))
    if _present(final):
        assignment = _read(final, binding)
        _require(not _present(pending))
        # An overlapping creator may have unlinked pending but not yet synced
        # that removal. Establish our own barrier before acknowledging reuse.
        _sync_directory(root)
        _require(not _present(pending) and _read(final, binding) == assignment)
        return assignment
    _require(create)
    return _publish(root, final, pending, binding)


def create_child_names(binding: ChildNameBinding) -> ChildNameAssignment:
    """Explicit first creation, or reuse an identical committed local intent.

    The caller establishes that this child is new. Local absence cannot prove
    that a child or provider allocation does not exist on another host/account.
    """
    try:
        return _load_or_create(binding, create=True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        failure = ChildNamingError("child naming intent is unavailable or conflicting")
    raise failure from None


def reopen_child_names(binding: ChildNameBinding) -> ChildNameAssignment:
    """Read existing intent; missing, partial or conflicting state stops here."""
    try:
        return _load_or_create(binding, create=False)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        failure = ChildNamingError("child naming intent is unavailable or conflicting")
    raise failure from None
