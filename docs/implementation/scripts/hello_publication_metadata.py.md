Please update alongside [hello_publication_metadata.py](../../../scripts/hello_publication_metadata.py).

Pure validation of captured provider JSON for the fixed Hello destination.
Package identity, type, private visibility and repository association are
conjunctive requirements. All paginated arrays must be structurally valid;
version IDs must be positive unique integers and tags unique strings. An empty
outer page collection is missing evidence; an empty page is a valid empty set.
Before push no version may carry the exact `hello-271-<full commit>` tag. After
push exactly one version must carry it and its digest must equal the canonical
exact-repository reference. Other tags are preserved, never deleted.

CLI accepts only before-push or published mode, reads files supplied by its shell
owner and emits bounded selected metadata. Invalid/missing data has a categorical
error without raw provider payloads. It does not perform network calls, grant
permission, prove pagination completeness itself, or authorize a retry. The shell
owner supplies complete successful gh responses; the producer supplies actual
image/tag/source correlation.
