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

Product SQL/connect timeouts bound database work. Polling has a 60-second budget;
an in-flight Docker RPC still uses the existing 30-second client timeout, so this
is not a hard 60-second execution deadline. An uncertain RPC is redacted and
stops without automatic retry. No stdout/stderr/password is saved in receipts.
Existing image-derived UID secret delivery, volume conflict refusal, retained
data ownership, pending observations and no-automatic-replay rules remain.
