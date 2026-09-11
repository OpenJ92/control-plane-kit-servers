Source: [scripts/cpk_server_source_live_abort.py](../../../scripts/cpk_server_source_live_abort.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This harness helper models a small checkpoint and caller-supplied ingress
ownership records, then orders authoritative cleanup before emergency fallback.
It owns neither provider authorization nor the cleanup implementation.

Checkpoint fields are bounded identifiers. record_checkpoint writes a sibling
temporary JSON file and replaces the destination before optional fault
injection. It does not fsync, enforce private permissions/symlink custody or
coordinate concurrent writers. Reading has no byte cap, tolerates extra fields
and ordinary JSON duplicate-key behavior, then reconstructs the selected fields.
A checkpoint is navigation evidence, not proof an external effect committed.

ExactOwnedIngressResource freezes a copied coordinate mapping and validates
selected fields, positive exact integers and a canonical bounded secret URI.
It does not establish record provenance, a closed provider/coordinate schema or
a total coordinate-count cap. bounded_descriptor omits the secret reference;
ordinary dataclass repr still includes that reference. Neither representation
is a universal sanitizer for caller-supplied coordinates.

compensate_abort requires emergency candidates to belong to the supplied
resource tuple. It attempts authoritative cleanup and then verifies absence
even if cleanup raised an ordinary exception; proven absence prevents fallback.
Otherwise it calls the provider-keyed emergency compensators for the selected
subset and verifies emergency absence. Returned failure stages, missing
providers, failed absence or an empty emergency subset retain uncertainty.
A raised compensator exception itself is not normalized here and can stop later
dispatch; BaseException is not covered by the ordinary-exception catches.

The result distinguishes authoritative from emergency completion, but does not
itself re-raise the original scenario failure: the invoking controller must
preserve that failure. No retry, provider call or deletion is hidden in this
module; callback ownership and exact evidence remain essential.

Related evidence: [abort tests](../../../products/cpk_server/tests/test_source_live_abort_compensation.py),
[phase reporting](cpk_server_source_live_report.py.md).
