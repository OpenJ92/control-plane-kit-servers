"""Offline root material projection/preparation; never starts services/providers.

Only explicit public commissioning snapshots are inputs. In particular this
module never loads commissioning PEMs or calls commissioning's private reuse.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import stat
import sys

from .bootstrap import RootBootstrapError, RootBootstrapHold, canonical, decode_document, plan_root_bootstrap

_INVALID = "root material preparation plan is invalid"
_HOLD = "root material preparation requires investigation"
_ROLES = ("human", "setup", "worker")
_FILES = {"control_credential": "setup.bearer", "postgres_password": "postgres.password",
    "custody_root_key": "custody.key", "provider_client_credential": "provider.token",
    "provider_credentials_document": "provider-credentials.json"}


def _require(condition):
    if condition is not True:
        raise ValueError


def _closed(value, keys):
    _require(type(value) is dict and value.keys() == set(keys))
    return value


def _provider_seed(subject, grants):
    # Secrets 158b17ed owns the initial-policy vocabulary. Its pure seed
    # validator needs typed grants but no bearer generation or database.
    from control_plane_kit_secrets.auth import ProviderCredential, ProviderGrant
    from control_plane_kit_secrets.provider_policy import _canonical_seed
    return _canonical_seed((ProviderCredential(subject=subject, token="",
        grants=tuple(ProviderGrant(grant["action"], grant["workspace_id"],
            tuple(grant["intents"])) for grant in grants)),))


def _commissioning(snapshot):
    """Verify public-only completion, exact bytes and actual role artifacts."""
    from .root_commissioning import _verified
    from control_plane_kit_core.configuration import ConfigurationArtifact
    from control_plane_kit_core.receiver_configuration import ReceiverNodeControlConfigurationCodec
    _closed(snapshot, {"plan", "intent_digest", "public_utf8", "public_sha256", "completion"})
    plan = _verified(snapshot["plan"], snapshot["intent_digest"], snapshot["plan"]["preparer_image_id"])
    _require(type(snapshot["public_utf8"]) is str)
    raw = snapshot["public_utf8"].encode("utf-8")
    _require(0 < len(raw) <= 65_536 and sha256(raw).hexdigest() == snapshot["public_sha256"])
    public = decode_document(raw)
    _closed(public, {"schema", "intent_digest", "receiver_ids", "artifacts", "public_keys", "completion_file"})
    complete = _closed(snapshot["completion"], {"schema", "intent_digest", "receiver_ids", "public_sha256"})
    _require(public["schema"] == "cpk.root-commissioning.public.v1"
        and complete["schema"] == "cpk.root-commissioning.complete.v1"
        and public["intent_digest"] == complete["intent_digest"] == plan["digest"]
        and complete["public_sha256"] == snapshot["public_sha256"]
        and public["completion_file"] == "complete.json")
    ids = _closed(public["receiver_ids"], {"cpk", "secrets"})
    _require(ids == complete["receiver_ids"] and len(set(ids.values())) == 2)
    _closed(public["artifacts"], {"cpk", "secrets"})
    _closed(public["public_keys"], set(plan["issuers"]))
    artifacts = {}
    for role in ("cpk", "secrets"):
        artifact = ConfigurationArtifact.from_descriptor(public["artifacts"][role])
        receiver = ReceiverNodeControlConfigurationCodec().decode_bytes(artifact.content.encode())
        target = receiver.target.descriptor()
        _require(target == {**plan["coordinates"][role], "receiver_id": ids[role]})
        families = {entry.purpose.value: entry for entry in receiver.verifiers}
        _require(families.keys() == plan["issuers"].keys())
        for purpose, family in families.items():
            metadata = _closed(public["public_keys"][purpose], {"issuer", "key_id", "public_key_sha256"})
            _require(len(family.public_keys) == 1)
            key, = family.public_keys
            _require(family.issuer == metadata["issuer"] == plan["issuers"][purpose]
                and key.key_id == metadata["key_id"]
                and sha256(key.public_key_pem.encode()).hexdigest() == metadata["public_key_sha256"])
        artifacts[role] = artifact
    return plan, artifacts


def _project(document, *, driver_image_id):
    """Pure public projection; generated values and private I/O are absent."""
    from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
    from control_plane_kit_core.policies import PolicyScope
    from control_plane_kit_core.products import ProductDescriptorCodec
    from control_plane_kit_operations.workspace_permissions import (
        GrantWorkspacePermissions, WorkspaceAdministrationContext,
    )
    from control_plane_kit_operations.workflows import IdempotencyKey
    from .workspace_authority_configuration import decode_workspace_authority_configuration
    from .bootstrap_workspace import workspace_intent_commitment
    from .root_commissioning import _absolute
    value = decode_document(canonical(document))
    _closed(value, {"schema", "bootstrap_input", "principals", "permissions", "capabilities",
        "management", "provider_grants", "custody", "commissioning"})
    _require(value["schema"] == "cpk.root-material.intent.v1")
    custody = _closed(value["custody"], {"host_directory", "uid", "gid"})
    _absolute(custody["host_directory"])
    _require(all(type(custody[key]) is int and 0 <= custody[key] <= 2**31 - 1 for key in ("uid", "gid")))
    commission, artifacts = _commissioning(value["commissioning"])
    output = Path(custody["host_directory"])
    read_trust = Path(commission["input"]["custody"]["host_directory"])
    # The shell mounts only the new private parent, never the old read-trust
    # directory (or an ancestor containing its private PEMs).
    _require(not output.is_relative_to(read_trust) and not read_trust.is_relative_to(output.parent))
    bootstrap = value["bootstrap_input"]
    installation = bootstrap["installation"]
    _require(not bootstrap.get("image_pull_credentials") and not installation.get("workspace_grants")
        and "workspace_authority" not in installation
        and installation["installation_id"] == commission["input"]["installation_id"]
        and installation["workspace_id"] == commission["input"]["workspace_id"])
    for role, expected in artifacts.items():
        product = ProductDescriptorCodec().decode_document(installation["products"][role]).product
        matches = tuple(item for item in product.runtime_contract.configuration_artifacts
            if item.artifact_id == expected.artifact_id or item.target_path == expected.target_path)
        _require(matches == (expected,))
    identities = _closed(value["principals"], _ROLES)
    _closed(value["permissions"], _ROLES)
    typed = {}
    for role, item in identities.items():
        _closed(item, {"issuer", "subject_id", "kind"})
        typed[role] = PrincipalIdentity(item["issuer"], item["subject_id"], PrincipalKind(item["kind"]))
        _require(item["issuer"] == "urn:control-plane-kit:static-development"
            and typed[role].kind is (PrincipalKind.WORKER if role == "worker" else PrincipalKind.OPERATOR))
    _require(len(set(typed.values())) == 3)
    policy = {"schema": "cpk-server.workspace-authority.v1", "installation_id": installation["installation_id"],
        "administrators": [identities["setup"]], "known_identities": [identities[role] for role in _ROLES],
        "capabilities": value["capabilities"]}
    policy_raw = canonical(policy)
    authority = decode_workspace_authority_configuration(policy_raw)
    context = WorkspaceAdministrationContext(typed["setup"], installation["installation_id"])
    seed = sha256(canonical(value)).hexdigest()[:24]
    grants = []
    for role in _ROLES:
        scopes = value["permissions"][role]
        _require(type(scopes) is list and bool(scopes) and len(set(scopes)) == len(scopes))
        key = "material-" + seed + "-" + role
        GrantWorkspacePermissions(context, installation["workspace_id"], typed[role],
            tuple(PolicyScope(scope) for scope in scopes), 0, IdempotencyKey(key))
        grants.append(dict(target=identities[role], scopes=scopes, expected_revision=0, idempotency_key=key))
    management = value["management"]
    if management is not None:
        _closed(management, {"runtime_id", "authority_ref", "capability_id"})
        _require(management["runtime_id"] == installation["installation_id"] + "-docker"
            and management["authority_ref"] == installation["runtime_authority"])
        authority.capability_policy.require(management["capability_id"])
        management = {**management, "expected_revision": 0, "idempotency_key": "material-" + seed + "-management",
            "registration_from": "command.runtime-authority.register"}
    administration = dict(workspace_creation_idempotency_key="material-" + seed + "-workspace",
        permission_grants=grants, management_grant=management)
    bootstrap["setup"]["administration"] = {"permission_grant_count": 3, "management_grant": management is not None}
    initialization_key = "material-" + seed + "-initialize"
    installation["workspace_authority"] = {"mode": "dynamic-v1", "private_intent_sha256": workspace_intent_commitment(
        policy_bytes=policy_raw, installer=identities["setup"], initialization_idempotency_key=initialization_key,
        public_setup=bootstrap["setup"], administration=administration)}
    _require(installation["control_auth"]["kind"] == "multi-principal")
    auth_reference = installation["control_auth"]["principals_document"]
    plan = plan_root_bootstrap(bootstrap, driver_image_id=driver_image_id)
    references = installation["references"]
    generated = {references[role]: filename for role, filename in _FILES.items()}
    generated[auth_reference] = "principals.json"
    _require(len(generated) == 6 and set(generated) == set(plan["required_material"]))
    provider_grants = value["provider_grants"]
    _require(type(provider_grants) is list and 1 <= len(provider_grants) <= 32)
    for grant in provider_grants:
        _closed(grant, {"action", "workspace_id", "intents"})
        _require(type(grant["action"]) is str and 1 <= len(grant["action"]) <= 128
            and grant["workspace_id"] == installation["workspace_id"]
            and type(grant["intents"]) is list and bool(grant["intents"])
            and all(type(intent) is str and 1 <= len(intent) <= 128 and intent != "*" for intent in grant["intents"]))
    _provider_seed("root-" + installation["installation_id"], provider_grants)
    private = {"plan_digest": plan["digest"], "policy": {"file": "workspace-authority.json", "sha256": sha256(policy_raw).hexdigest()},
        "installer": identities["setup"], "initialization_idempotency_key": initialization_key,
        "administration": administration}
    return value, plan, generated, policy_raw, private


def plan_root_material_preparation(document, *, driver_image_id):
    try:
        value, bootstrap, files, _, _ = _project(document, driver_image_id=driver_image_id)
        # Preserve the caller's pre-projection public input, never a second
        # projection with an already-authored authority commitment.
        original = decode_document(canonical(document))
        result = {"schema": "cpk.root-material.plan.v1", "input": original,
            "driver_image_id": driver_image_id, "bootstrap_plan": bootstrap,
            "files": files, "outputs": [*files.values(), "human.bearer", "worker.bearer",
                "workspace-authority.json", "index.json", "bootstrap-input.json", "bootstrap-plan.json"]}
        result["digest"] = sha256(canonical(result)).hexdigest()
        return result
    except Exception:
        failure = RootBootstrapError(_INVALID)
    raise failure


def _write(directory, name, raw, mode=0o400):
    _require(type(raw) is bytes and 0 < len(raw) <= 1_048_576)
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        mode, dir_fd=directory)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    os.fsync(directory)


def verify_root_material_plan(plan, *, expected_digest, driver_image_id, host_state, uid, gid):
    """Pure preflight for the normal shell entrance, before host mkdir."""
    try:
        expected = plan_root_material_preparation(plan["input"], driver_image_id=driver_image_id)
        custody = expected["input"]["custody"]
        _require(plan == expected and expected_digest == expected["digest"]
            and host_state == custody["host_directory"] and type(uid) is int and type(gid) is int
            and (uid, gid) == (custody["uid"], custody["gid"]))
        return expected
    except Exception:
        failure = RootBootstrapError(_INVALID)
    raise failure


def prepare_root_material(plan, *, expected_digest, driver_image_id, state_directory, host_state=None):
    """Fresh exclusive output. Partial or existing state is held, never reused."""
    try:
        _require(isinstance(state_directory, Path)
            and state_directory.is_absolute())
        expected = verify_root_material_plan(plan, expected_digest=expected_digest, driver_image_id=driver_image_id,
            host_state=str(state_directory) if host_state is None else host_state,
            uid=os.geteuid(), gid=os.getegid())
        if host_state is not None:
            _require(state_directory.parent == Path("/preparation")
                and state_directory.name == Path(host_state).name and state_directory.name not in {"", ".", ".."})
    except Exception:
        failure = RootBootstrapError(_INVALID)
    else:
        return _prepare(expected, state_directory)
    raise failure


def _prepare(plan, state):
    directory = None
    try:
        from .root_commissioning import _directory
        from .bootstrap_runtime import _material_document
        from .server import CpkServerBootstrapConfiguration, _credential_verifier
        from .workspace_authority_configuration import decode_workspace_authority_configuration
        from control_plane_kit_secrets.crypto import encode_master_key_for_file
        _, bootstrap, files, policy_raw, private = _project(plan["input"], driver_image_id=plan["driver_image_id"])
        _require(bootstrap == plan["bootstrap_plan"])
        custody = plan["input"]["custody"]
        state.mkdir(mode=0o700, parents=False, exist_ok=False)
        directory = _directory(state, custody["uid"], custody["gid"])
        parent = os.open(state.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        _write(directory, "intent.json", canonical({"preparation_digest": plan["digest"],
            "bootstrap_plan_digest": bootstrap["digest"]}), 0o600)
        # No private commissioning files or existing credentials are opened.
        tokens = {role: secrets.token_urlsafe(48) for role in _ROLES}
        provider = secrets.token_urlsafe(48)
        principal_rows = [{"credential": tokens[role], "subject_id": plan["input"]["principals"][role]["subject_id"],
            "kind": plan["input"]["principals"][role]["kind"], "workspace_grants": {}} for role in _ROLES]
        values = dict(control_credential=tokens["setup"], postgres_password=secrets.token_urlsafe(48),
            custody_root_key=encode_master_key_for_file(os.urandom(32)), provider_client_credential=provider,
            provider_credentials_document=json.dumps([{"subject": "root-" + bootstrap["input"]["installation"]["installation_id"],
                "token": provider, "grants": plan["input"]["provider_grants"]}]))
        for role, filename in _FILES.items():
            _write(directory, filename, values[role].encode())
        _write(directory, "human.bearer", tokens["human"].encode())
        _write(directory, "worker.bearer", tokens["worker"].encode())
        _write(directory, "principals.json", canonical(principal_rows))
        _write(directory, "workspace-authority.json", policy_raw)
        _write(directory, "bootstrap-input.json", canonical(bootstrap["input"]))
        _write(directory, "bootstrap-plan.json", canonical(bootstrap))
        index = {"schema": "cpk.root-bootstrap.material.v2", "files": files, "dynamic_workspace": private}
        # No consumable index pathname exists while validation is incomplete.
        material, admitted = _material_document(bootstrap, index, state / "index.json")
        from control_plane_kit_secrets.bootstrap import load_provider_credentials
        from control_plane_kit_secrets.auth import ProviderAuthorizer, ProviderGrant
        from control_plane_kit_secrets.provider_policy import _canonical_seed
        credentials = load_provider_credentials({"CPK_SECRETS_CREDENTIALS_FILE": str(state / "provider-credentials.json")})
        provider_authorizer = ProviderAuthorizer(credentials)
        authenticated_provider = provider_authorizer.authenticate("Bearer " + provider)
        # This validates prepared credentials, not active request-time policy.
        # The pinned Secrets authorizer owns authentication only.
        _require(len(credentials) == 1 and authenticated_provider is credentials[0]
            and authenticated_provider.subject == "root-" + bootstrap["input"]["installation"]["installation_id"]
            and authenticated_provider.grants == tuple(ProviderGrant(grant["action"],
                grant["workspace_id"], tuple(grant["intents"])) for grant in plan["input"]["provider_grants"])
            and authenticated_provider.capabilities == ()
            and _canonical_seed(credentials) == _provider_seed(authenticated_provider.subject,
                plan["input"]["provider_grants"]))
        installation = bootstrap["input"]["installation"]
        node = next(node for node in bootstrap["resources"]["nodes"] if node["node_id"] == bootstrap["cpk_node_id"])
        environment = {**node["environment"], "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON":
            material[installation["control_auth"]["principals_document"]]}
        authority = decode_workspace_authority_configuration(policy_raw)
        config = CpkServerBootstrapConfiguration._from_environment(environment, workspace_authority=authority)
        verifier = _credential_verifier(config)
        from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
        for role in _ROLES:
            requested = plan["input"]["principals"][role]
            identity = PrincipalIdentity(requested["issuer"], requested["subject_id"], PrincipalKind(requested["kind"]))
            _require(verifier.authenticate(tokens[role].encode()).identity == identity
                and (identity in authority.administration_policy.administrators) == (role == "setup"))
        _require(admitted.installer.identity == authority.administration_policy.administrators[0])
        result = {"schema": "cpk.root-material.complete.v1", "preparation_digest": plan["digest"],
            "bootstrap_plan_digest": bootstrap["digest"], "commissioning_intent_digest":
                plan["input"]["commissioning"]["intent_digest"],
            "commissioning_public_sha256": plan["input"]["commissioning"]["public_sha256"],
            "identities": plan["input"]["principals"], "outputs": plan["outputs"]}
        _require(set(os.listdir(directory)) == (set(plan["outputs"]) - {"index.json"}) | {"intent.json"})
        _write(directory, "complete.new", canonical(result), 0o600)
        os.rename("complete.new", "complete.json", src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
        # acquire_root consumes the canonical index directly. Make it visible
        # only after all validation and the completed receipt are durable.
        _write(directory, "index.new", canonical(index))
        os.rename("index.new", "index.json", src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
        return result
    except Exception:
        failure = RootBootstrapHold(_HOLD)
    finally:
        if directory is not None:
            os.close(directory)
    raise failure


def _read_public(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        metadata = os.fstat(descriptor)
        _require(stat.S_ISREG(metadata.st_mode) and 0 < metadata.st_size <= 1_048_576)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(1_048_577)
        _require(0 < len(raw) <= 1_048_576)
        return raw
    finally:
        os.close(descriptor)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "root material arguments are invalid\n")


def main(argv=None):
    parser = _Parser()
    sub = parser.add_subparsers(dest="action", required=True)
    planning = sub.add_parser("plan")
    for name in ("input", "commission-plan", "commission-public", "commission-complete", "public-sha256", "commissioning-digest", "driver"):
        planning.add_argument("--" + name, required=True)
    preparing = sub.add_parser("prepare")
    for name in ("plan", "digest", "driver", "state"):
        preparing.add_argument("--" + name, required=True)
    preparing.add_argument("--host-state")
    verification = sub.add_parser("verify")
    for name in ("plan", "digest", "driver", "host-state", "uid", "gid"):
        verification.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            document = decode_document(_read_public(args.input))
            _require("commissioning" not in document)
            document["commissioning"] = {"plan": decode_document(_read_public(args.commission_plan)),
                "intent_digest": args.commissioning_digest, "public_utf8": _read_public(args.commission_public).decode(),
                "public_sha256": args.public_sha256, "completion": decode_document(_read_public(args.commission_complete))}
            result = plan_root_material_preparation(document, driver_image_id=args.driver)
        elif args.action == "verify":
            plan = verify_root_material_plan(decode_document(_read_public(args.plan)), expected_digest=args.digest,
                driver_image_id=args.driver, host_state=args.host_state, uid=int(args.uid), gid=int(args.gid))
            result = {"preparation_digest": plan["digest"], "bootstrap_plan_digest": plan["bootstrap_plan"]["digest"]}
        else:
            result = prepare_root_material(decode_document(_read_public(args.plan)), expected_digest=args.digest,
                driver_image_id=args.driver, state_directory=Path(args.state), host_state=args.host_state)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print(_INVALID if args.action == "plan" else _HOLD, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
