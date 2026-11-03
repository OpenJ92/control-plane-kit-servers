#371 adds only optional http_status and diagnostic fields to existing result envelopes. Old valid journals remain valid. Read/write validation requires unverified advancement and exact still-pending workspace/run/plan/idempotency binding, independently of transport ingestion. Invalid stored evidence refuses; no new schema version, sidecar or durable server record is introduced. Source review and the complete normal Docker gate passed at fdacc9405138e9b25b4c2928a3d5c13b9a7ecdae; required CI remains pending.

The gate passed all 1,260 product tests plus 26 test-support tests, compilation,
clean import and the normal smoke/cleanup stages. See [the complete result and
scoped cleanup limits](https://github.com/OpenJ92/control-plane-kit-servers/issues/371#issuecomment-6598347612).
Earlier pending-validation statements below describe historical slices.

# `client/journal.py`

`topology-client-preparation.v1` extends the existing private invocation journal
without changing file-v1 or saved-v1 meanings. Its `preparation` descriptor names
only `<operation_ref>.graph.json` and records the exact size and SHA-256.

The graph artifact is published with the same owned-partial, hard-link,
directory-fsync discipline as journal creation. It is never replaced. Reads
require a current-user-owned regular nonsymlink `0600` file, exact name, bounded
size, stable inode/metadata, and matching digest. The artifact is published
before the journal; a crash in between can leave bounded local residue but no
server or runtime mutation.
