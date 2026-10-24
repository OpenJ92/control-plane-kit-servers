Source: [live_postgres_image.py](../../../../../products/postgres_server/tests/live_postgres_image.py).

The original source-built ladder also accepts an explicitly borrowed published
artifact. Selection precedes fixture creation; all containers use the resolved
immutable ID. The lifecycle/retained-row checks and native-listener-before-SQL
ordering remain shared. Resource cleanup is inside exercise's finally; borrowed
fixture cleanup and ownership-aware image cleanup complete before success output.
Borrowed images are never removed, including on failure. Source image deletion
additionally checks the tag still identifies the owned image.
Before fixtures or lifecycle effects, existing named or labelled containers,
volumes and networks refuse without adoption or cleanup. Only newly returned
objects from the admitted invocation enter cleanup lists.
See [artifact procedure](../../../../managed-postgres-artifacts.md).
