# `client/workflow.py`

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

The extraction stays inside the fresh-introductions branch. Retained-only,
pending-only and gateway-route-only authoring keeps `verifier_configuration=None`
and does not perform a verifier read. This preserves the existing optional-read
boundary rather than referencing an unassigned response for zero introductions.

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
