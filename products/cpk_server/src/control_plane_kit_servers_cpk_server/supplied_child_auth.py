"""Private admission of the externally supplied #379 child verifier profile.

The caller already holds all embedded credentials. This adapter performs no IO
and returns no credential, verifier, grant or evidence of deployed identity.
"""
import json

from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind

from .server import _static_principals
from .workspace_authority_configuration import decode_workspace_authority_configuration


class SuppliedChildAuthError(ValueError):
    """Fixed refusal without protected parser context."""

    def __init__(self):
        super().__init__("supplied child authentication configuration is invalid")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError


def _documents_match(*, child_installation_id, administrator, initializer,
                     browser, verifier_document, authority_document):
    """Private parse/comparison frame returns before the public refusal."""
    try:
        identities = (administrator, initializer, browser)
        if (any(type(identity) is not PrincipalIdentity for identity in identities)
                or len(set(identities)) != 3
                or browser.kind is not PrincipalKind.OPERATOR
                or type(child_installation_id) is not str
                or not child_installation_id
                or type(verifier_document) is not bytes
                or not 1 <= len(verifier_document) <= 131_072):
            raise ValueError
        document = json.loads(verifier_document.decode("ascii"),
            object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        if (type(document) is not list or len(document) != 3
                or any(type(entry) is not dict or set(entry) != {
                    "credential", "subject_id", "kind", "workspace_grants"}
                    for entry in document)):
            raise ValueError
        # Structural restrictions are profile-local; existing parser owns the
        # bearer, kind and grant semantics and credential uniqueness checks.
        principals = _static_principals(json.dumps(document), allow_empty_grants=True)
        actual = tuple(entry.principal.identity for entry in principals)
        if (len(set(actual)) != 3 or set(actual) != set(identities)
                or any(entry.principal.workspace_grants for entry in principals)):
            raise ValueError
        authority = decode_workspace_authority_configuration(authority_document)
        policy = authority.administration_policy
        if (policy.installation_id != child_installation_id
                or policy.administrators != (administrator,)
                or set(policy.known_identities) != set(identities)):
            raise ValueError
        return True
    except (ValueError, TypeError, AttributeError, UnicodeError, RecursionError, OverflowError):
        return False


def validate_child_auth_documents(*, child_installation_id, administrator,
                                  initializer, browser, verifier_document,
                                  authority_document):
    """Compare supplied documents without retaining material in denial frames.

    Success establishes only document correspondence. The caller separately
    establishes custody/version provenance and current child association before
    material resolution or authenticated requests. Caller-owned input lifetime
    remains the caller's responsibility; no memory-zeroization claim is made.
    """
    accepted = _documents_match(child_installation_id=child_installation_id,
        administrator=administrator, initializer=initializer, browser=browser,
        verifier_document=verifier_document, authority_document=authority_document)
    # Do not retain even the original argument references in this frame when it
    # becomes part of a public exception traceback. Parsed copies stayed private.
    verifier_document = authority_document = None
    if not accepted:
        raise SuppliedChildAuthError()
    return None
