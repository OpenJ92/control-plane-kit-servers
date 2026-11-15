# Isolated persistence test design

Review proposal for Servers #417/#408, depending on CPK #2093. This document
does not itself authorize a run or claim persistence evidence. North released
combined candidate `e4bc1275aa3378ecc4e8c32c7872d3f0a4a2ef0c` for isolated
cross-repository qualification after Meridian verified source preservation,
full Core and focused Operations tests. Hosted qualification is separate.
Existing discovery publication
and installed-run boundaries remain in force.

## Smallest harness change

Extend the existing root `./test.sh` named-cohort path rather than add a runner,
service installation, release witness, or host database. The proposed
`topology-authoring` cohort retains all current grandparent source verification
and preservation tests, using the independently reviewed X pins. After the
ordinary socket-free source tests pass, run one additional database-backed MCP
test module in that same source-sealed test image.

Use the established PostgreSQL 16 disposable fixture pattern from Operations
`test.sh` and `tests/draft_catalogue_fixture.py`: internal Docker network,
unpublished database port, tmpfs database storage, bounded health admission,
`CPK_OPERATIONS_TEST_DATABASE_URL`, real schema installation and real
`PostgresUnitOfWork`. No installed database, named durable volume, image push,
provider, runtime interpreter, daemon socket, or host Python enters the test
container. Database connection values are synthetic test-only inputs and must
not be printed in receipts.

Implement resource handling inside a subshell in `test.sh`, so its local trap
cannot replace the outer cohort source-context cleanup trap. Create a unique
run identifier and label both the database and test containers and network.
Record full created resource IDs before subsequent actions. Admit the network
as internal and the database as unpublished before running the test. Keep the
existing image selection; this is a test database, not a server-product image
qualification.

Root `test.sh:cleanup_numeric_bootstrap` and
`scripts/postgres_artifact_shell.sh:cleanup_owned` provide the stronger cleanup
pattern: check the exact retained ID and ownership label, remove only that
resource, then query for verified absence. Do not copy older smoke scripts'
fixed names, pre-run deletion, or error-swallowing cleanup. Remove the test
container, database container, and then empty network. Tmpfs avoids a separate
volume. Preserve the original test failure; cleanup failure also makes the
overall gate fail. Missing creation IDs, label/identity mismatch, failed
inspection, or ambiguous creation stop as unknown and retain receipts without
guessing a resource name or automatically retrying. No global prune occurs.

## Real owner fixture and public entrance

Reuse the owner fixture's schema/unit-of-work setup and cleanup, not its command
helpers as the authoring path. A unique per-test schema gives independent
workspaces and synthetic registered product documents. Existing precreated
fixture sessions, if retained, are baseline setup and must be excluded from the
walkthrough's new-session assertions. No fake catalogue, draft owner, graph
store, or scripted successful reply supplies persistence evidence.

Use the existing actual Servers ASGI host and released MCP client in auto and
legacy modes. Replace only fixture authentication/composition wiring, using the
real `CpkServerReadService`, `CpkServerLifecycleService`, planning service,
product authoring service, draft command service and operation command service
over the real unit of work. Existing deterministic token fixtures are local
test inputs. Use the same current grants and owners for the HTTP comparator.
Do not call the owner directly to perform the walkthrough save.

The normal public sequence is active product list/detail, preview, session
start, first save, then exact saved revision read. Every response coordinate
used by the next request comes from that actual response. A second owner
connection can inspect bounded truth for assertions; it cannot substitute for
the public readback.

## Acceptance criteria

1. Both SDK eras discover the closed schemas and correct read/mutation hints.
   The grandparent read-only profile still advertises exactly four reads and
   refuses the three new tools, including direct calls.
2. Preview two registered product pins with explicit public settings, one
   unbound Docker runtime and one compatible edge. Compare its HTTP result
   with MCP; graph/session/action/draft/revision/runtime facts do not change.
   Fixed verification values and canonical descriptor bytes stay absent.
3. Start a new session through the public tool once; save its recipe and the
   actual preview commitment once. Require a complete owner receipt containing
   workspace, draft, revision and graph. Do not assume revision 1 or select the
   latest draft by title.
4. Read the receipt's exact revision through MCP and HTTP. Require equal public
   results, exact receipt identity, both product identities and descriptor
   digests, runtime membership and edge endpoints/protocol. Current and Desired
   graph pointers remain at the baseline. The new session/action and draft
   revision are durable in a separate unit of work.
5. Compare input/schema failures, missing/current revoked grants, foreign
   workspace/pins and stale commitment with HTTP. No refused request publishes
   a graph/draft/revision; current permissions are checked on each call. Owner
   tests retain transaction, concurrent replay, and registration semantics;
   Servers need not reproduce that state machine.
6. Inject loss after the ASGI application has completed session start but before
   its reply reaches the SDK. Assert one dispatch and one durable new session;
   stop before save, with no draft publication and no automatic resend. The
   fixture can know stored truth for assertions; the client still reports an
   unknown result and does not recover a session ID through private access.
7. Independently lose the first-save response after completion. Assert one
   dispatch and one durable saved revision, no second save, no selection or
   deployment. The caller has no receipt and reports unknown. Do not turn the
   fixture's private knowledge into a public recovery claim.
8. When a full save receipt was actually received, exact readback may be repeated
   and must not mutate state. Revision attempt history can legitimately be empty;
   do not create deployment work to populate it.
9. Invalid authentication, malformed/oversized requests, and bounded safe errors
   preserve the existing host boundary. Rejected input and server diagnostics
   never reflect canary private values. No test skips for a missing database or
   missing owner contract; these are gate failures with candid classification.
10. Test failure still triggers owned cleanup. Report fixture exit, test exit,
    schema cleanup, container/network absence and source-context cleanup
    separately. Cleanup uncertainty cannot become a passing gate.

## Evidence and limits

The receipt records Servers source, complete cohort, imported source checks,
test cases/SDK modes, terminal exit, and owned cleanup results. Source tests are
not installed/native-client evidence. PostgreSQL setup writes and schema
cleanup are confined to the newly created disposable fixture. No live token,
installation, permission, image publication or provider operation is included.

The smallest code surface is the finite cohort admission/selection extension,
one sequential database stage in `test.sh`, and one owned test module plus its
fixture setup. Reuse existing host/client fixtures and owner services. Avoid
changing the production app solely to inject test state. Meridian reviews this
design, preservation of the existing cohort guard, and owned cleanup before the
new apparatus is run. CPK #2093 supplies X and its package-level evidence.
