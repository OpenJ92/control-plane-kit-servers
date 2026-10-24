Source: [test_postgres_publication.py](../../../../../products/postgres_server/tests/test_postgres_publication.py).

Product-owned source laws cover destination, repository-matched visibility/unused tag,
immutable artifact admission, no fallback and borrowed-image preservation,
and cleanup-before-success ordering. The publisher test uses command fakes to
exercise its real shell and pure policy across preflight/build/push/post-check
failures without Docker or registry effects. These tests do not qualify an image.
Review regressions prove same-basename receipt paths receive distinct random
identities and existing named/labelled resources refuse before creation, fixture
mutation or removal.

First-publication tests preserve the default404 refusal and exercise the visibly
distinct selector against exact package404, package200/appeared-before-push,
auth/transient/transport/malformed failures, versions404 and post-push
visibility/repository/tag/digest/candidate mismatch. Pure parser tests reject invalid
exit status, duplicate JSON keys and oversized input. All external commands are
fakes inside the owning Docker-backed source suite; no package is created.

Visibility-match laws cover both public and private repositories, exact repository
identity, consistent visibility/private fields, package association ID/name, both
mismatch directions and pre-push/post-push repository drift. Existing provenance,
single-push and borrowed-image/cleanup laws remain in the same owning suite.
