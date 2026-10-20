# Managed witness failure diagnostics

Source: [test_managed_witness_diagnostics.py](../../../../../products/cloudflared_connector/tests/test_managed_witness_diagnostics.py).

Servers #284 diagnostic plan received Meridian and Kepler PLAN PASS after
gate39381573535 lost the detached helper's specific failure observation.
Five focused methods cover closed reason selection with candidate canaries,
nonzero completion with valid/missing/invalid records, deadline exhaustion
before file opening, unchanged success and zero-exit/failure inconsistency,
and mode-restricted best-effort failure writing.
The write test asserts True for successful retention, False for excluded modes
without writing, and False with no output for a candidate-bearing write error.

The tests substitute only result retrieval or record writing at the existing
witness boundary. The deadline case uses the actual reader. They do not model
Docker internals, native lifetime, or SDK behavior. Existing automatic product
test discovery collects them; no collection or skip configuration changes.
The993b61b gate stopped at integrity before these methods executed.
Gate39385659976 on10720fa subsequently passed integrity and all five methods as
part of752 passing package methods. Runtime qualification still failed with a
generic outer message and no helper/controller record.

The next fixed-marker correction adds four methods at actual witness functions:
capture freezes primary context before cleanup changes and clears requested
helper mode outside observation; publication rejects candidate-bearing context;
terminal selection preserves the original exception despite cleanup failure
and refuses cleanup-only failure; failed emission retains the frozen context
and original outcome. Existing helper-result laws remain unchanged.
No Docker state machine or runtime success is simulated.

Nine diagnostic methods now exist. The four new methods and changed controller
have not executed. Only the owning Docker `./test.sh` can validate this local
correction after exact source review and North's next run release; no supported
narrow local entrypoint exists and no alternate harness is introduced.
