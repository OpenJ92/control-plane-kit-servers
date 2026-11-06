The complete #371 source slice now adopts accepted Operations 9822cab5831c0cb7f8584a99607812b07cc346b6 and propagates optional validated HTTP status/diagnostic through ClientResult. The workflow independently rebinds injected transport evidence to pending intent before saving. Unresolved status retains only bound evidence without dispatch; the existing bound-success transition removes stale optional evidence before its normal pending-clear write. Existing phase, coordinates, history, idempotency, save-failure uncertainty and retry authority remain unchanged. The combined reporting/propagation source passed review and the complete normal Docker gate at fdacc9405138e9b25b4c2928a3d5c13b9a7ecdae; required CI remains pending.

The gate passed all 1,260 product tests plus 26 test-support tests, compilation,
clean import and the normal smoke/cleanup stages. See [the complete result and
scoped cleanup limits](https://github.com/OpenJ92/control-plane-kit-servers/issues/371#issuecomment-6598347612).
Earlier pending-validation statements below describe historical slices.

# `client/workflow.py`

The independent #371 reporting slice handles a lost or invalid final advancement
response by deriving execution status from the existing journal phase and saving
bounded attention with advancement unverified. It changes only last_result;
pending intent/idempotency, successful request history, coordinates and executed
phase remain intact, with no redispatch. Authorization errors keep their existing
path. A failed attention save raises the existing bounded JournalError, reporting
both advancement and persistence as unverified; replacement may already have
occurred before directory fsync, so no retry, restoration or saved/absent claim is
made. The existing result schema is unchanged in this slice. Source review and
consolidated green remain pending; Operations pins are not changed here.

`TopologyClient.plan` keeps its existing file and saved-revision paths and adds
`AuthoredDesiredGraph`. The authored path reads workspace fences, requests exact
receiver context, reads only required public verifier families, performs the pure
pre-wire transform, canonicalizes the complete graph, persists it, journals the
request, and only then dispatches.

The context response must echo the exact five requested workspace expectation
fields before verifier reads, identity generation, preparation persistence, or
dispatch. This is a correlation check over owner evidence, not a duplicate owner
state machine.

Prepared retry rereads the original file solely to compare path, byte size, and
SHA-256. The outgoing graph comes only from the immutable preparation artifact,
which must also decode and re-encode to identical canonical Core graph bytes.
Identity factories, context reads, verifier reads, and route composition are
never invoked on replay.

The public workload-verifier read is the flattened Operations
`FocusedDetailReadModel.descriptor()`: `workspace_id`, `kind` and
`workload_verifier_configuration` are siblings. After validating workspace/kind,
the client extracts only that top-level configuration mapping into the exact
input envelope expected by `author_receiver_graph`. It does not read a `payload`
field or accept a nested compatibility shape. Missing/non-mapping fields refuse
before fresh receiver identity generation or prepare dispatch; the pure authoring
owner retains all verifier family, purpose, key and declaration checks.

The extraction runs only for fresh introductions or explicit current-receiver
verifier refreshes. One authenticated read requests the union of purposes needed
by those declarations; the pure transform selects each declaration's families.
Retained-only without refresh, pending-only and gateway-route-only authoring keep
`verifier_configuration=None` and do not perform a verifier read. Refresh uses the
existing immutable preparation journal and restart path without new state or
retry semantics. The mixed introduction/refresh test proves purpose selection at
the authoring boundary, not mixed-change planner acceptance.

Explicit declaration updates pass through the same pure transform and exact
preparation journal. They preserve installed verifier families and do not add a
public-key read. The coupled wrapper/routes graph is persisted before prepare;
lost-response replay reads those exact bytes without reauthoring or reselection.
Existing source-drift and preparation-integrity checks remain authoritative.

Completed apply replay revalidates public plan, approval, run, events and current
selection without repeating execution or graph advancement. Both `advanced`
and `converged` phases bypass the pre-advancement block after public validation;
the final desired-current comparison remains required.

For those completed phases, public status starts execution and advancement as
`unverified`. Fresh run evidence and exact current graph/projection evidence
promote the observations independently. An unavailable early read cannot inherit
historical success from the journal; unavailable or changed current selection
after successful run verification reports succeeded execution with unverified
advancement. Apply's initial plan/approval read failures likewise report
unverified completed advancement. Other phase defaults, pending recovery, exact
approval and execution confirmations, and authorization exceptions are unchanged.
