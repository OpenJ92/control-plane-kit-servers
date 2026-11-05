# Supplied child authentication: proposed first slice

Governing issue: Servers #379. Tests-only source checkpoint for independent
review; production adapter and executable validation are pending.

Base and destination: roadmap/1813-runtime-control at
883f08298d4864199ca450b19d5cbd500e6168e7. Branch: codex/379-supplied-auth.
Core 7afef43f, Operations 885513e3, Interpreters 685c8627, SDK 220f6316,
Secrets 09442303 remain selected. Operations and root bootstrap are unchanged.

## Proposed private interface

`supplied_child_auth.validate_child_auth_documents` takes keyword-only
`child_installation_id`, three typed `PrincipalIdentity` values named
`administrator`, `initializer`, `browser`, and two protected byte inputs named
`verifier_document` and `authority_document`. Success returns None; refusal is
the fixed, detached `SuppliedChildAuthError`. Nothing is serialized or retained.

This function runs only in the privileged configuration-admission boundary that
is already allowed to read the combined document. That caller holds every
embedded identity's credential power. Enrollment and setup clients never receive
the combined document; each consumes its own supplied credential separately.

Reuse the actual Servers static principal parser with empty grants enabled and
the existing workspace-authority decoder. Check exactly three distinct intended
full identities, one entry each, empty static grants, unique valid credentials,
matching child installation, exactly the administrator in administrators, and
exactly the three identities in known_identities. This profile adds restrictions
without changing the generic verifier or root bootstrap semantics.

## Source trace reused and refreshed

`installation.MultiPrincipalControlAuth` selects only the protected document
reference for the child verifier. `server._static_principals` parses bearer and
typed identity values; `workspace_authority_configuration` decodes policy.
`bootstrap_workspace.admit_workspace_intent` already authenticates a supplied
administrator and checks policy membership, but targets root bootstrap inputs.
`bootstrap_enrollment.permission_receipt` uses a subset check for root grants;
later child adapters must compare exact intended resulting scopes and revision
without altering the root helper.

The proposed validator closes only the exact-profile correspondence gap. It
performs no file, resolver, network, store, permission, issuance or delivery I/O.
It cannot prove a supplied byte string came from a claimed reference/version or
that a deployed child received it. Those claims require existing owner evidence.

## Offline proof and subsequent prerequisite

The tests use synthetic bytes and check acceptance, role/identity mismatch,
duplicate/missing/extra principals, extra static grants, duplicate bearer,
policy mismatch and detached redacted errors. The ordinary Docker-backed
`./test.sh` owns executable evidence. This checkpoint has not run it and is
expected to lack the proposed adapter. No behavioral red is claimed.

Kepler's test revision additionally checks a sole but wrong administrator,
an extra policy-only known identity, conflicting duplicate credential/subject
keys, an unexpected field on an otherwise valid entry, and valid JSON padded
past the byte limit. A profile-local structural pass must reject duplicate keys
and nonclosed entry shapes before reusing the existing parser for semantics;
the generic process parser is unchanged. The public interface check is separate
from the behavioral class's module prerequisite. Missing-interface evidence is
never classified as a denied-profile behavioral result.

The next integration step must bind approved parent custody workspace/provider,
reference/version, child installation, canonical API origin and policy to
authoritative current child/ingress evidence before resolving any credential.
Accepted ChildNameAssignment supplies local planned names only. A hostname/TLS
match, an arbitrary evidence dict, or a caller's boolean cannot establish the
child association. No supported current-child evidence producer is demonstrated
in the selected source; that automation remains unsupported until a concrete
existing owner artifact is identified. No network or resolver seam is added in
this first slice, so the absent prerequisite does not broaden its authority.

Later receipt adapters reuse Operations typed create/grant/revoke records and
compare exact actor, child workspace, target, revision and resulting sets.
Initializer has seven temporary setup scopes and then an empty set; browser has
workspace-read only. Revocation of workspace permission leaves authentication
valid. External supplier owns token lifecycle, assembly and customer delivery.

Review requested: Meridian for interface/test ownership; Kepler for privileged
document consumption and authority. No production edits or gate before review.

Focused implementation release: North relayed Kepler/Meridian clearance of the
corrected tests. The issue's browser-role law specifically requires OPERATOR.
The generic static parser accepts operator/service/worker; the selected Operations
workspace read route policies admit OPERATOR. The validator must reject even a
WORKER browser that matches its verifier and policy entries. Exact correspondence
to the three supplier-designated typed identities is necessary but insufficient
for that role law. Admission still proves no usable browser, permission or live
destination. The red checkpoint deliberately omits only this browser-kind rule
to demonstrate the corresponding behavioral failure through the owning gate.
