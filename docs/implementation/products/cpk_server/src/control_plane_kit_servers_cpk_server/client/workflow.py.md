Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

TopologyClient sequences public preparation, approval, admission, run and
current-graph commands. Operations owns sessions, desired revision admission,
authorization, plans, leases and durable execution; the local journal owns
transport provenance and replay locators. The default transport selects Core's
public routes at this package's actual dependency pin. Report and draft methods
delegate to their separate owners.

Plan accepts either an opaque JSON object from a regular file (at most 64 KiB)
or SavedDesiredRevision's exact bounded draft ID and positive revision. File
reading rejects duplicate keys and nonstandard JSON constants, uses final-path
no-follow where supported, and retains absolute path/size/raw digest instead
of the graph body. It does not validate topology or permission admission, check
private file ownership, or secure all ancestor/race conditions. Saved input
contains coordinates, not graph content.

Fresh preparation reads workspace current/desired pointers and desired
generation, allocates a new invocation/key, then journals before HTTP. Saved
preparation requires a selected desired pointer and nonzero generation and
retains the exact request. Its returned plan is checked against the submitted
fences and workspace; file mode checks recorded plan coordinates after they
exist rather than applying that same initial saved-source correlation.
resume_prepare only replays pending preparation. It preserves the original
key/fences; file replay must re-read the same source and reconstruct the same
request digest. It does not choose the newest draft, select a revision, rebase
or open a replacement server session.

Apply requires the exact recorded plan ID even for pending replay, refreshes
plan/approval evidence and uses the invocation's advisory mutation lock.
A pending approval requires the exact ordinary or destructive approval flag
and rejects the opposite kind. Already approved evidence follows a different
path; client flags do not grant server scopes. Operator credentials prepare
and admit, approver credentials decide, and worker credentials claim, start,
execute and advance. Claim's route run_id carries the execution-request ID;
later routes carry the returned run ID and claim generation.

Each mutation records its pending key/body digest before dispatch, then stores
selected response coordinates before continuing. Response binding is
route-specific: admission only requires a bounded execution-request ID,
whereas claim/start/execute/advance check their respective identifiers,
generation or outcome fields. This is not universal envelope/foreign-key
validation. Authorization failures propagate; transport uncertainty or a
mismatched reply preserves the pending on-disk request and returns attention.
Journal failure after an HTTP effect has no cross-system rollback.

Existing runs trigger public status reads before pending replay, but an
attention result does not universally prevent replay when a pending request
exists. Exact request replay relies on the server's public idempotency and
execution contracts; it is not a provider safety decision or permission to
redispatch effects directly. Successful progress uses a new key for each
max_effects=1 command. The 128-record journal budget and bounded execution loop
limit request count, not total elapsed time. Blocked, failed, unsupported,
uncertain and in-flight outcomes stop the loop with attention.

Execution completion and graph advancement are separate. Advancement checks
the current base, submits desired pointers/generation, then reads the public
current graph before recording convergence. Failed readback can preserve
succeeded execution with unverified advancement. Converged is a local result
supported by these public receipts/readbacks, not a fresh provider or health
witness. Repeated apply after convergence is not promised as a no-op: the
advancement path skips only the advanced phase.

Status issues reads without taking the mutation lock or writing the invocation;
JournalStore.read may initialize directories. It refreshes plan changes and
approval scope instead of trusting last_result, and retains attention for
pending commands. History traversal allows at most 16 pages of 100 items,
bounds opaque cursors and rejects repetition. These reads are non-atomic and
do not perform the stronger report owner's complete association checks.

ClientResult supplies the v1 descriptor and attention exit 4; other statuses
map to exit 0. Its frozen fields are not full constructor validation or deep
immutability. Produced projections omit raw graph/credential/history bodies,
but bounded strings, private paths/titles and chained exceptions are not
universal secret sanitization. Health/freshness remain unknown here.

Related source and evidence: [products/cpk_server/tests/test_topology_client.py](../../../../../../../products/cpk_server/tests/test_topology_client.py), [products/cpk_server/tests/test_topology_client_saved.py](../../../../../../../products/cpk_server/tests/test_topology_client_saved.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/report.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/report.py), [pyproject.toml](../../../../../../../pyproject.toml).
