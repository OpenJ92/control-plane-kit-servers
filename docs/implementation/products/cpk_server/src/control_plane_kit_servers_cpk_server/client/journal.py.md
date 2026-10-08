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
