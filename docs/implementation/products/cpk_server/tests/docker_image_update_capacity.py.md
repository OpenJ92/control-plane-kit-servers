# Archived publication-capacity diagnostic — #1993 / #252

Historical source: [docker_image_update_capacity.py at 3e544bff](https://github.com/OpenJ92/control-plane-kit-servers/blob/3e544bff50f3ff6d179b8d000496b216f92a84cd/products/cpk_server/tests/docker_image_update_capacity.py).

The temporary observer and its four observer-only tests are removed after the
full maintained workload passed at `3e544bff50f3ff6d179b8d000496b216f92a84cd`.
The scoped import/context is removed; every workload assertion remains. Final
source still requires its normal owning gate before merge. This document retains
historical evidence, not an active runtime hook.

[Successful gate 39008332385](https://github.com/OpenJ92/control-plane-kit-servers/actions/runs/39008332385)
recorded content at 4,228 settled / 4,229 peak records, within the accepted 8,192
policy. Content pre-ID peak accounted bytes were 10,640,839 and snapshot 264,348;
bound peak was 8,185,604. All initial/update/replay/no-op/public teardown assertions
passed. Public teardown removed containers/network; exact fixture disposal then
removed seven historical configuration volumes and one secret volume. Direct log
SHA-256: `f93512a03b4ff6d61e0a829dcd5dda776ec673f6dd336e3ffb2f886d7b4b58e0`.
Kepler independently verified the result. Native/ingress remain synthetic; this
is not grandparent or production Cloudflare acceptance.

Historical implementation and failed-checkpoint notes follow.

Temporary #1993 diagnostic observes the actual accepted Operations owner's pure
publication forecast during the unchanged #252 Docker scenario. It calls the
original `_publication_budgets` once and returns that exact tuple. `_preflight`
and its refusal remain unchanged. The accepted owner tests already establish
that this forecast performs no SQL and does not change accounting; no second
forecast, owner-state reconstruction or additional evidence read is introduced.

At most eight records expose fixed numeric prior/snapshot/future/publication and
combined settled/peak footprints plus the owner's closed capacity decision.
Each record is limited to 16 KiB; integers are nonnegative signed-64-bit values.
The phase is pre-id or bound. No identifiers, graph/history contents, SQL,
credentials or secret material are read for output. Output errors cannot replace
the original owner's return or refusal; the method patch always restores.
Emission returns an explicit success/failure boolean, retained in the context's
bounded outcome list. Owner exceptions never enter that diagnostic handler.

The first diagnostic checkpoint `91eef9b` stopped in package integrity before
build or behavioral execution: its bare exception-swallowing branch violated the
test-source scanner. The corrected emitter follows the existing failure-evidence
helper's explicit outcome convention, with strengthened outcome assertions. No
scanner exemption or weakening is used; that failed gate collected no capacity
measurements and dispatched no scenario effects.

Socket-free tests prove tuple/exception identity, exact once invocation, numeric
schema/count bounds, canary exclusion, untouched preflight, restoration and
preservation of its actual capacity refusal when printing fails. These are
diagnostic contracts, not acceptance-state or capacity-correctness simulations.
The normal hosted owning gate provides the one released real-route measurement.
The observer was temporary until diagnosis and the owner regression were
captured. A measured excess did not authorize a cap increase or production fix.

The first Operations #1994 adoption gate at `46cba82` stopped in the socket-free
package suite: two diagnostic tests still expected 4,097 records to refuse under
the former policy. No runtime witness or capacity measurement ran. The fixture
now uses the literal approved 8,192-record publication peak plus prior 1, and
asserts exactly 8,193 combined records. Both the `record-limit` decision and the
actual owner's `_Capacity` refusal remain required, along with all diagnostic
identity, restoration, output and redaction laws. Observer and production source
are unchanged. The corrected checkpoint still requires the normal full gate.
