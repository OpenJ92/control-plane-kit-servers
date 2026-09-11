Source: [scripts/cpk_server_source_live_report.py](../../../scripts/cpk_server_source_live_report.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This helper emits JSON-line phase records with process-local sequence numbers,
bounded identifier fields and closed health/key/access/resource values.
Constructor checks reject selected secret-shaped markers. It serializes no
free-form exception message in ordinary phase failure handling.

Actions run sequentially. The first caught failure marks later phases skipped,
calls cleanup once and raises SourceLiveRunFailed retaining the primary code
and optional cleanup code. Unknown ordinary exceptions become fixed codes;
a malformed action result becomes phase-result-malformed. A successful run
returns its evidence and does not call cleanup automatically.

These claims assume valid trusted objects and a functioning ledger sink.
started/succeeded writes and failure-reporting writes sit outside the action's
protected region; a write/flush failure can interrupt reporting or prevent
cleanup. BaseException is not caught. Subclassed or mutated evidence is not
revalidated on descriptor emission, so the closed shape is not a hostile-object
security boundary.

flush is not durable fsync or an Operations transaction. Sequence numbers reset
for a new ledger and concurrent writers are not coordinated. A cleanup callback
return is reported as resource_stage=removed without independent verification
in this module; the callback must establish absence. These records supplement
server history and do not prove provider state, credential authority or cleanup
convergence on their own.

Related evidence: [phase tests](../products/cpk_server/tests/test_source_live_phase_reporting.py.md),
[abort helper](cpk_server_source_live_abort.py.md).
