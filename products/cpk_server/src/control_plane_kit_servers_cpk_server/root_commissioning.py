"""Explicit offline first-root read trust; no graph or provider authority."""
from __future__ import annotations

import argparse
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Mapping
import uuid

from .bootstrap import RootBootstrapError, RootBootstrapHold

MAX_BYTES = 65_536
MAX_KEY_BYTES = 4096
PURPOSE_FILES = {
    "workload-node-control-surface-read": "surface-read.pem",
    "workload-node-health-read": "health-read.pem",
}
MODES = {"lock": 0o600, "intent.json": 0o600, "receivers.json": 0o600,
         "surface-read.pem": 0o400, "health-read.pem": 0o400,
         "public.json": 0o600, "complete.json": 0o600}
_PLAN_ERROR = "root commissioning plan is invalid"
_HOLD = "root commissioning custody requires investigation"


def _require(condition):
    if not condition:
        raise ValueError


def _canonical(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    _require(0 < len(raw) <= MAX_BYTES)
    return raw


def _object(value, keys):
    _require(type(value) is dict and set(value) == set(keys))
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError


def _decode(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_invalid_constant)


def _absolute(value):
    _require(type(value) is str and 1 < len(value.encode("utf-8")) <= 4096)
    _require(value.startswith("/") and all(part not in ("", ".", "..") for part in value.split("/")[1:]))
    _require(not any(character in value for character in ("\x00", "\n", "\r", ",")))
    return value


def _products():
    # These dependencies belong only to commissioning, never ordinary bootstrap
    # planning or an optional absent configuration path.
    from .control_configuration import cpk_control_declaration, cpk_control_configuration_artifact
    from control_plane_kit_secrets.control import secrets_control_declaration
    from control_plane_kit_servers_secrets_server.configuration import secrets_control_configuration_artifact
    return {"cpk": (cpk_control_declaration(), cpk_control_configuration_artifact),
            "secrets": (secrets_control_declaration(), secrets_control_configuration_artifact)}


def plan_root_commissioning(document: Mapping[str, object], *, preparer_image_id: str) -> dict:
    """Pure bounded projection; allocates no identity and opens no custody."""
    try:
        from control_plane_kit_core.node_control import NodeControlGraphReference, NodeControlGraphReferenceRole
        from .installation import _INSTALLATION_ID, _WORKSPACE_ID
        value = _decode(_canonical(document))
        _object(value, {"schema", "installation_id", "workspace_id", "profile", "custody"})
        _require(value["schema"] == "cpk.root-commissioning.intent.v1")
        _require(value["profile"] == "operator-offline-read-trust")
        installation, workspace = value["installation_id"], value["workspace_id"]
        _require(type(installation) is str and type(workspace) is str)
        _require(len(installation) <= 48 and _INSTALLATION_ID.fullmatch(installation))
        _require(_WORKSPACE_ID.fullmatch(workspace))
        custody = _object(value["custody"], {"host_directory", "uid", "gid"})
        _absolute(custody["host_directory"])
        for name in ("uid", "gid"):
            _require(type(custody[name]) is int and 0 <= custody[name] <= 2**31 - 1)
        _require(type(preparer_image_id) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", preparer_image_id))
        roles = NodeControlGraphReferenceRole
        coordinates = {}
        for role, (declaration, _) in _products().items():
            coordinate = {"workspace_id": workspace, "runtime_id": installation + "-docker",
                          "node_id": installation + "-" + role,
                          "provider_socket_name": declaration.surface.provider_socket_name.value}
            for name, reference_role in (("workspace_id", roles.WORKSPACE), ("runtime_id", roles.RUNTIME),
                                         ("node_id", roles.NODE), ("provider_socket_name", roles.PROVIDER_SOCKET)):
                NodeControlGraphReference(reference_role, coordinate[name])
            coordinates[role] = coordinate
        issuers = {purpose: installation + "-offline-" + suffix
                   for purpose, suffix in zip(PURPOSE_FILES, ("surface-read", "health-read"))}
        _require(all(len(issuer.encode()) <= 128 for issuer in issuers.values()))
        plan = {"schema": "cpk.root-commissioning.plan.v1", "input": value,
                "preparer_image_id": preparer_image_id, "coordinates": coordinates, "issuers": issuers}
        plan["digest"] = sha256(_canonical(plan)).hexdigest()
        _canonical(plan)
        return plan
    except Exception:
        failure = RootBootstrapError(_PLAN_ERROR)
    raise failure


def _verified(plan, digest, image):
    try:
        candidate = _decode(_canonical(plan))
        expected = plan_root_commissioning(candidate["input"], preparer_image_id=image)
        _require(candidate == expected and type(digest) is str and digest == expected["digest"])
        return expected
    except Exception:
        failure = RootBootstrapError(_PLAN_ERROR)
    raise failure


def _identity(info, uid, gid, mode, *, directory=False):
    _require((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode))
    _require((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (uid, gid, mode))
    if not directory:
        _require(info.st_nlink == 1)


def _directory(path, uid, gid):
    # Walk without following any symlink, then retain an fd for every operation
    # inside custody. The launcher separately validates host ancestry ownership.
    _absolute(str(path))
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in path.parts[1:]:
            next_descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                      dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        _identity(os.fstat(descriptor), uid, gid, 0o700, directory=True)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _read(directory, name, uid, gid):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
    try:
        before = os.fstat(descriptor)
        _identity(before, uid, gid, MODES[name])
        maximum = MAX_KEY_BYTES if name.endswith(".pem") else MAX_BYTES
        _require(before.st_size <= maximum)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(descriptor)
        _require(len(raw) <= maximum and (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                 (after.st_size, after.st_mtime_ns, after.st_ctime_ns))
        return raw
    finally:
        os.close(descriptor)


def _write(directory, name, raw, mode):
    _require(type(raw) is bytes and len(raw) <= (MAX_KEY_BYTES if name.endswith(".pem") else MAX_BYTES))
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         mode, dir_fd=directory)
    try:
        # Never change an existing entry; the fd was exclusively created here.
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(directory)


def _render(plan, receivers, private_keys, key_ids):
    import control_plane_kit_core as core
    from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    _object(receivers, {"cpk", "secrets"})
    _require(len(set(receivers.values())) == 2)
    _object(key_ids, PURPOSE_FILES)
    families, metadata = [], {}
    for purpose, private in private_keys.items():
        _require(isinstance(private, Ed25519PrivateKey))
        public = private.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
        public_key = core.DelegationPublicKey(key_ids[purpose], core.DelegationKeyAlgorithm.ED25519, public)
        issuer = plan["issuers"][purpose]
        families.append(NodeControlVerificationConfiguration(core.DelegationKeyPurpose(purpose), issuer, (public_key,)))
        metadata[purpose] = {"issuer": issuer, "key_id": key_ids[purpose],
                             "public_key_sha256": sha256(public.encode()).hexdigest()}
    artifacts = {}
    roles = core.NodeControlGraphReferenceRole
    for role, (declaration, factory) in _products().items():
        coordinate = plan["coordinates"][role]
        target = core.NodeControlReceiverTarget(
            *(core.NodeControlGraphReference(reference_role, coordinate[name]) for name, reference_role in (
                ("workspace_id", roles.WORKSPACE), ("runtime_id", roles.RUNTIME),
                ("node_id", roles.NODE), ("provider_socket_name", roles.PROVIDER_SOCKET))), receivers[role])
        artifacts[role] = factory(core.ReceiverNodeControlConfiguration(target, declaration, tuple(families))).descriptor()
    result = {"schema": "cpk.root-commissioning.public.v1", "intent_digest": plan["digest"],
              "receiver_ids": receivers, "artifacts": artifacts, "public_keys": metadata,
              "completion_file": "complete.json"}
    _canonical(result)
    return result


def _completion(plan, receivers, public_raw):
    return {"schema": "cpk.root-commissioning.complete.v1", "intent_digest": plan["digest"],
            "receiver_ids": receivers, "public_sha256": sha256(public_raw).hexdigest()}


def _reuse(directory, plan, uid, gid):
    from cryptography.hazmat.primitives import serialization
    _require(set(os.listdir(directory)) == set(MODES))
    saved = {name: _read(directory, name, uid, gid) for name in MODES}
    _require(saved["lock"] == b"" and saved["intent.json"] == _canonical(plan))
    receivers = _decode(saved["receivers.json"])
    _require(saved["receivers.json"] == _canonical(receivers))
    public = _decode(saved["public.json"])
    private_keys = {purpose: serialization.load_pem_private_key(saved[name], password=None)
                    for purpose, name in PURPOSE_FILES.items()}
    key_ids = {purpose: public["public_keys"][purpose]["key_id"] for purpose in PURPOSE_FILES}
    expected = _render(plan, receivers, private_keys, key_ids)
    _require(saved["public.json"] == _canonical(expected))
    _require(saved["complete.json"] == _canonical(_completion(plan, receivers, saved["public.json"])))
    return expected


def _prepare_locked(plan, state):
    directory = lock = None
    try:
        custody = plan["input"]["custody"]
        uid, gid = custody["uid"], custody["gid"]
        _require((os.geteuid(), os.getegid()) == (uid, gid))
        directory = _directory(state, uid, gid)
        entries = set(os.listdir(directory))
        # Reject unknown/incomplete custody before creating even a lock entry.
        _require(entries <= {"lock"} or entries == set(MODES))
        if "lock" in entries:
            lock = os.open("lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        else:
            try:
                lock = os.open("lock", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                               0o600, dir_fd=directory)
            except FileExistsError:
                # A contender may have created only the shared fixed lock.
                lock = os.open("lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        _identity(os.fstat(lock), uid, gid, 0o600)
        _require(os.fstat(lock).st_size == 0)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        entries = set(os.listdir(directory))
        if entries == set(MODES):
            return _reuse(directory, plan, uid, gid)
        _require(entries == {"lock"})
        os.fsync(lock)
        os.fsync(directory)
        # The durable incomplete marker precedes all identity/key allocation.
        _write(directory, "intent.json", _canonical(plan), 0o600)
        receivers = {role: uuid.uuid4().hex for role in ("cpk", "secrets")}
        _write(directory, "receivers.json", _canonical(receivers), 0o600)
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import secrets
        private_keys, key_ids = {}, {}
        for purpose, name in PURPOSE_FILES.items():
            private = Ed25519PrivateKey.generate()
            private_keys[purpose] = private
            key_ids[purpose] = "key-" + secrets.token_hex(16)
            raw = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
            _write(directory, name, raw, 0o400)
        result = _render(plan, receivers, private_keys, key_ids)
        public_raw = _canonical(result)
        _write(directory, "public.json", public_raw, 0o600)
        # Verify persisted private/public correspondence before committing. No
        # private-file hash is stored, returned, logged or used as identity.
        stored_keys = {purpose: serialization.load_pem_private_key(_read(directory, name, uid, gid), password=None)
                       for purpose, name in PURPOSE_FILES.items()}
        _require(_canonical(_render(plan, receivers, stored_keys, key_ids)) == public_raw)
        _require(_read(directory, "public.json", uid, gid) == public_raw)
        _require(_read(directory, "receivers.json", uid, gid) == _canonical(receivers))
        _require(_read(directory, "intent.json", uid, gid) == _canonical(plan))
        _write(directory, "complete.new", _canonical(_completion(plan, receivers, public_raw)), 0o600)
        _require(set(os.listdir(directory)) == (set(MODES) - {"complete.json"}) | {"complete.new"})
        os.rename("complete.new", "complete.json", src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
        return result
    except Exception:
        failure = RootBootstrapHold(_HOLD)
    finally:
        if lock is not None:
            os.close(lock)
        if directory is not None:
            os.close(directory)
    raise failure


def _prepare(plan, state):
    # Include descriptor closure failures in the same detached public boundary.
    try:
        return _prepare_locked(plan, state)
    except Exception:
        failure = RootBootstrapHold(_HOLD)
    raise failure


def prepare_root_commissioning(plan: Mapping[str, object], *, expected_digest: str,
                              preparer_image_id: str, state_directory: Path) -> dict:
    """Prepare the approved exact path, or verify completed state without writes."""
    verified = _verified(plan, expected_digest, preparer_image_id)
    try:
        _require(isinstance(state_directory, Path))
        _require(str(state_directory) == verified["input"]["custody"]["host_directory"])
    except Exception:
        failure = RootBootstrapError(_PLAN_ERROR)
    else:
        return _prepare(verified, state_directory)
    raise failure


def _input_file(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        _require(stat.S_ISREG(os.fstat(descriptor).st_mode) and os.fstat(descriptor).st_size <= MAX_BYTES)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return _decode(stream.read(MAX_BYTES + 1))
    finally:
        os.close(descriptor)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error can echo arbitrary supplied argument values.
        self.exit(2, "root commissioning arguments are invalid\n")


def main(argv=None):
    parser = _Parser(description="Explicit offline root read-trust commissioning")
    commands = parser.add_subparsers(dest="action", required=True)
    planning = commands.add_parser("plan")
    planning.add_argument("--input", required=True)
    planning.add_argument("--preparer", required=True)
    preparation = commands.add_parser("prepare")
    for name in ("plan", "digest", "preparer", "state"):
        preparation.add_argument("--" + name, required=True)
    preparation.add_argument("--host-state")
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            result = plan_root_commissioning(_input_file(args.input), preparer_image_id=args.preparer)
        else:
            plan = _verified(_input_file(args.plan), args.digest, args.preparer)
            if args.host_state is None:
                result = prepare_root_commissioning(plan, expected_digest=args.digest,
                    preparer_image_id=args.preparer, state_directory=Path(args.state))
            else:
                # Only the launcher knows host-to-container transport. Preserve
                # the saved host intent rather than rewriting it to /commissioning.
                _require(_absolute(args.host_state) == plan["input"]["custody"]["host_directory"])
                result = _prepare(plan, Path(_absolute(args.state)))
        print(_canonical(result).decode("utf-8"))
        return 0
    except Exception:
        print(json.dumps({"status": "hold", "message": _HOLD}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
