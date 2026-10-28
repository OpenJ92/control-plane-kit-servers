Source: [bootstrap_runtime.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py).

Root acquisition interprets the verified plan with the existing Docker SDK.
Configuration volumes participate in initial occupancy checks and the ordinary
ownership receipt. The SDK's archive is root-owned, so owner-only configuration
requires a root recipient image user; nonroot recipients are refused before
network/volume acquisition. Read-only public configuration retains its declared
mode without introducing a new ownership or permission API.

Each volume is recorded before materialization. Pending intent survives SDK
exceptions or a content-digest mismatch. Digest observations attest only bytes;
the SDK owns archive mode realization and the real numeric recipient fixture
independently verifies mode, readability and write denial. Recipient inspection
must match the full secret/configuration read-only content-subpath mount set
before start. A mount mismatch retains the created recipient ID and pending
intent. Existing receipts prevent automatic replay or adoption.

Docker operations are nontransactional. Existing exclusive state-directory
locking and atomic receipt writes remain the concurrency boundary; separately
invoked state directories are not a distributed lock. There is no automatic
rollback. Configuration volumes follow existing retained-resource ownership and
exact-ID cleanup. Public initialization still uses authenticated CPK routes;
this path neither grants managed-health execution nor qualifies new images.

#302 enabled plans select only their two derived loopback bindings. After each
start/reload, before clearing start intent, actual SDK published_ports must equal
the complete expected tuple (sorted without deduplication): exactly one for
API/website, empty for PostgreSQL/Secrets. Only after equality are bounded
fixed-field mappings persisted under observations.host_bindings[node_id], while
start remains pending; the existing observed() then clears it. Errors preserve
uncertainty. Pre-start image/mount checks and the website-absent branch remain
unchanged. This proves local publication only, not external reachability.
# Managed PostgreSQL startup (#327)

The validated managed password-file contract selects authenticated SQL startup.
The driver uses the PostgreSQL owner's `psql_invocation`, with the resolved
password only in the exec environment, stderr disabled, and exact exit-zero /
`1\n` evidence. A listening port or successful `pg_isready` is insufficient.
SQL startup is distinct from signed wrapper readiness. Native startup is unchanged.

Product SQL/connect timeouts bound database work, but Docker's attached stream
does not inherit a reliable HTTP read timeout. This synchronous Linux CLI uses a
scoped raising SIGALRM to interrupt each managed SQL observation after at most
10 seconds or the remaining 60-second polling budget. It refuses a non-main
thread or existing real timer before exec, then disarms/restores the prior signal
handler in finally. SDK stream=False closes its response during unwinding.
An interrupted observation is a redacted HOLD without another exec or acquisition
advancement. It does not prove the remote SQL command was cancelled. No
stdout/stderr/password is saved in receipts.
Existing image-derived UID secret delivery, volume conflict refusal, retained
data ownership, pending observations and no-automatic-replay rules remain.

Before acquisition, managed shared password material rejects trailing LF,
in addition to existing empty/NUL/invalid-encoding refusal. The product's generic
file reader strips LF while CPK environment delivery preserves it; rejecting this
ambiguous bootstrap input keeps PostgreSQL, CPK and probe bytes identical without
rewriting the shared secret map. Native-root material behavior is unchanged.

# Protected dynamic admission and delivery (#345)

The dynamic-only v2 material index adds a protected policy sibling and private
administration intent. Static input still requires v1. Private admission returns
credentials separately from a repr-hidden snapshot, verifies the plan/commitment,
whole policy catalogue and actual setup bearer through the process verifier,
and uses Operations administration/grant validators. Rejected private parser
context is discarded. A prior acquisition receipt still wins before file reads.

`installer_files` joins occupancy checks, image numeric-UID selection, protected
0400 staging and the complete recipient read-only mount comparison. Staging
consumes the admitted byte snapshot, never reopens the private policy filename.
Only safe UID/mode/verified observations are recorded. The installation policy
volume is not one of the disposable setup plan/credential volumes.

At the intermediate #345 boundary, public dynamic apply returned
`dynamic-bootstrap-incomplete` after valid private admission and before Docker.
The final #347 source candidate removes that intermediate guard and uses the
existing initialization/public setup composition. Invalid material and prior
receipts still refuse before acquisition. The candidate remains unvalidated;
source inspection and earlier component results do not establish current-image
dynamic installation acceptance or execution history.

#346 reserves initialization helper names during dynamic occupancy inspection and
records absence of the exact PostgreSQL data volumes. After authenticated database
readiness, the private controller path invokes explicit schema/binding initialization
before any application node. The #346 hook alone was not a usable bootstrap
release; the #347 integrated source and actual-image gate own that connection.
The existing receipt remains the owner of pending and bounded helper observations.

#347 stages the minimized public-helper files from the admitted snapshot. Their
exact names join conflict detection, numeric-owned protected delivery, read-only
mounts and exact completed-helper cleanup. No acquisition target or database
password is delivered to public setup. The progress reader admits bounded receipt,
assignment and observed-graph identifiers, nonnegative exact-integer revisions
and closed active/revoked states; private identities, keys and policy remain absent.
The integrated guard change requires independent review and the current-image
launcher gate before acceptance. It creates no additional live authority.
