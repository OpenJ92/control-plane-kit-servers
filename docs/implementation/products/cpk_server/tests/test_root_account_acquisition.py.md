Source: [test_root_account_acquisition.py](../../../../../products/cpk_server/tests/test_root_account_acquisition.py).

The command's admission laws reject wrong repository, mutable reference, malformed
producer and a missing producer-job context before acquisition/output creation.
Credential canaries must not enter stdout/stderr. These tests run only through
the normal owning Docker suite; they do not create mounts, contact registries,
run Docker controllers or prove a successful publication/inspection/cleanup.

Review exposed two concrete defects: failed empty inventories could be interpreted
as absence, and the checkout source mount could include persisted Git credentials.
The added process-boundary laws exercise failed Docker/mount/loop queries and
require nonzero exit with no candidate promotion/backing removal; a mount-query
error also blocks loop detach. Separate metadata/offline invocation tests capture
actual Docker arguments using a failing process double and require the narrow
script-only source mount. They never simulate a successful unpack or read real
credentials. These synthetic targets run inside the normal Docker suite.

Three diagnostic methods exercise the actual offline wrapper and parent status
writer with process doubles: every allowed phase and conservative outer failure
must reach existing status.json as HOLD without a candidate or cleanup; absent,
mismatched, embedded, duplicate, truncated and oversized markers must remain
unknown; and candidate promotion still requires successful execution, bounded
nonempty output and observed container absence. The success-transport fixture is
an explicitly opaque synthetic receipt, not successful unpack/account evidence.
The parser consumes at most128 bytes of private diagnostics and exports only
fixed labels. These additions require their own source review and owning gate.

The retained-publication connection adds four synthetic methods. Source admission
requires the fixed target/producer and a distinct exact clean diagnostic checkout,
while preserving the same-job equality rule. A failed controller pull is attempted
once, records a bounded HOLD with separate source/run identities, and cannot
inspect/promote/clean up; same-job mode makes no pull. The real entrypoint's dirty
preparation path leaves bounded prior-publication/provenance records before any
controller call. Git/Docker are process doubles inside the owning Docker suite;
they do not prove an actual pull, token scope, quota, successful unpack or cleanup.
The fourth checks the actual mutually exclusive job-selection and explicit
read-only diagnostic permission declarations, then exercises all four retained/
same-job boolean combinations through source admission. Only retained=true with
same-job=false is admitted; the other combinations cannot enter that diagnostic.
Static workflow declarations do not constitute an executed GitHub job inventory.
