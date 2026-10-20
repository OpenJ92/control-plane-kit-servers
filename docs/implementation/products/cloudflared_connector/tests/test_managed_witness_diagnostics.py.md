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

## Approved package-lane target preparation

Jacob approved source/package checks now and mandatory positive CPK/Cloudflare
acceptance after integration, with all laws retained on #284. Both reviewers
accepted two narrow target additions before implementation:

- One table-driven method calls the actual image_contents boundary with either
  wrong UID or wrong GID. It requires numeric_uid refusal before the version
  subprocess; the patched subprocess raises a fixed assertion if reached.
  Metadata/file reads occur later, so this boundary must stop them too.
- The existing deadline method also requires exit-zero completion with an expired
  deadline to refuse before opening the result file. Its nonzero case remains.

This is a target-only checkpoint on e0402db source: the numeric admission is
missing, so expected causal red is reaching the guarded version-call boundary
in both UID/GID cases. The expiry case protects an existing law and need not
fail. No executable red has been observed yet. The nine prior diagnostic
methods remain intact; artifact/mode translation follows only with the later
package implementation. There are ten diagnostic methods at this checkpoint.
No runtime witness, shell gate or production source has changed.
