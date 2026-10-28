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
