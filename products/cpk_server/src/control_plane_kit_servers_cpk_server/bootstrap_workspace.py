"""Admission of the root installer's private workspace intent; no external I/O."""

from dataclasses import dataclass, field
import hashlib

from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_operations.workflows import IdempotencyKey, InvalidOperationCommand
from control_plane_kit_operations.workspace_permissions import (
    GrantWorkspacePermissions, WorkspaceAdministrationContext, _key, _revision, _text,
)
from control_plane_kit_operations.managed_runtime_assignments import _reference

from .bootstrap import _closed, canonical
from .operations_application import WorkspaceAuthorityConfiguration
from .workspace_authority_configuration import decode_workspace_authority_configuration


@dataclass(frozen=True, slots=True, repr=False)
class AdmittedWorkspaceIntent:
    """Private snapshot. Never serialize into a plan, receipt or progress report."""

    policy_bytes: bytes = field(repr=False)
    authority: WorkspaceAuthorityConfiguration = field(repr=False)
    installer: WorkspaceAdministrationContext = field(repr=False)
    initialization_key: IdempotencyKey = field(repr=False)
    administration_bytes: bytes = field(repr=False)


def workspace_intent_commitment(*, policy_bytes, installer, initialization_idempotency_key,
                                public_setup, administration):
    """Pure correspondence hash; neither possession nor hashing grants authority."""
    return hashlib.sha256(canonical({
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
        "installer": installer, "initialization_idempotency_key": initialization_idempotency_key,
        "setup_sha256": hashlib.sha256(canonical({"public_setup": public_setup,
            "administration": administration})).hexdigest(),
    })).hexdigest()


def _identity(value):
    _closed(value, {"issuer", "subject_id", "kind"})
    return PrincipalIdentity(value["issuer"], value["subject_id"], PrincipalKind(value["kind"]))


def _command_key(value):
    try:
        return _key(IdempotencyKey(value))
    except InvalidOperationCommand:
        failure = ValueError("private command key is invalid")
    raise failure


def admit_workspace_intent(plan, private, policy_bytes, credentials):
    """Caller has bounded private bytes; reuse process and Operations validators."""
    from .server import CpkServerBootstrapConfiguration, _credential_verifier
    from .managed_health_configuration import _managed_health_configuration_from_artifact
    from control_plane_kit_core.configuration import ConfigurationArtifact

    _closed(private, {"plan_digest", "policy", "installer", "initialization_idempotency_key", "administration"})
    _closed(private["policy"], {"file", "sha256"})
    installation, setup = plan["input"]["installation"], plan["input"]["setup"]
    if (private["plan_digest"] != plan["digest"]
            or private["policy"]["sha256"] != hashlib.sha256(policy_bytes).hexdigest()
            or installation["workspace_authority"]["private_intent_sha256"] != workspace_intent_commitment(
                policy_bytes=policy_bytes, installer=private["installer"],
                initialization_idempotency_key=private["initialization_idempotency_key"],
                public_setup=setup, administration=private["administration"])):
        raise ValueError("private intent differs")
    authority = decode_workspace_authority_configuration(policy_bytes)
    if authority.administration_policy.installation_id != installation["installation_id"]:
        raise ValueError("policy installation differs")
    if "managed_health_configuration" in installation:
        health = _managed_health_configuration_from_artifact(
            ConfigurationArtifact.from_descriptor(installation["managed_health_configuration"]),
            dynamic_workspace=True)
        if {binding.capability for binding in health.capability_bindings} != set(authority.capability_policy.capabilities):
            raise ValueError("health catalogue differs")

    # Compile the real selected authentication inputs. The internal parser has
    # no file/provider effects; the policy is the already decoded byte snapshot.
    node = next(node for node in plan["resources"]["nodes"] if node["node_id"] == plan["cpk_node_id"])
    environment = dict(node["environment"])
    auth = installation.get("control_auth", {"kind": "single-operator"})
    bearer = credentials[installation["references"]["control_credential"]]
    if auth["kind"] == "multi-principal":
        environment["CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"] = credentials[auth["principals_document"]]
    else:
        environment["CPK_CONTROL_AUTH_STATIC_CREDENTIAL"] = bearer
    config = CpkServerBootstrapConfiguration._from_environment(environment, workspace_authority=authority)
    verified = _credential_verifier(config).authenticate(bearer.encode("ascii"))
    if verified.identity != _identity(private["installer"]):
        raise ValueError("installer credential differs")
    context = authority.administration_policy.authorize(verified)
    initialization_key = _command_key(private["initialization_idempotency_key"])
    administration = private["administration"]
    _closed(administration, {"workspace_creation_idempotency_key", "permission_grants", "management_grant"})
    _command_key(administration["workspace_creation_idempotency_key"])
    grants = administration["permission_grants"]
    summary = setup["administration"]
    if (type(grants) is not list or len(grants) != summary["permission_grant_count"]
            or (administration["management_grant"] is not None) != summary["management_grant"]):
        raise ValueError("administration summary differs")
    for grant in grants:
        _closed(grant, {"target", "scopes", "expected_revision", "idempotency_key"})
        target = _identity(grant["target"])
        authority.administration_policy.require_known(target)
        if type(grant["scopes"]) is not list:
            raise ValueError("invalid scopes")
        GrantWorkspacePermissions(context, installation["workspace_id"], target,
            tuple(PolicyScope(scope) for scope in grant["scopes"]), grant["expected_revision"],
            _command_key(grant["idempotency_key"]))
    management = administration["management_grant"]
    if management is not None:
        _closed(management, {"runtime_id", "authority_ref", "capability_id", "expected_revision",
            "idempotency_key", "registration_from"})
        # No fabricated registration ID: validate only pre-registration fields.
        _text(management["runtime_id"])
        _reference(RuntimeAuthorityReference(management["authority_ref"]))
        authority.capability_policy.require(management["capability_id"])
        _revision(management["expected_revision"])
        _command_key(management["idempotency_key"])
        if (management["registration_from"] != "command.runtime-authority.register"
                or management["runtime_id"] != installation["installation_id"] + "-docker"
                or management["authority_ref"] != installation["runtime_authority"]):
            raise ValueError("registration intent differs")
    return AdmittedWorkspaceIntent(policy_bytes, authority, context, initialization_key, canonical(administration))
