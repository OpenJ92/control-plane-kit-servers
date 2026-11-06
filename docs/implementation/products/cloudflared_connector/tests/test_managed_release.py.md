# Managed release boundary tests

#225 result-volume targets exercise the normal, contents and candidate shell
owners with command doubles. A shared run-owned volume is created before the
controller, mounted without copying image contents, and removed only after exit.
Removal failure, retained results, mismatched provisional receipt and interrupted
promotion cannot qualify. Cleanup verification preserves a failed witness outcome;
interruption after atomic promotion does not undo already verified cleanup facts.
These are orchestration targets, not actual Docker volume evidence.
The normal-shell target checks a separate closed cleanup record for successful
and failed invocations, preserves the primary nonzero exit when cleanup also
fails, and requires a single volume-removal attempt.
Preflight negatives also return empty listings or expected-looking image metadata
with nonzero command status: every affected owner must stop before build, run or
volume acquisition/removal. This tests admission separately from later finalization.

Command doubles prove routing and refusal ordering only. Missing, mutable and duplicate selected-image inputs must refuse before Docker I/O or unrelated full-gate setup. They do not prove image qualification, publication or real native connection. Run through the owning Docker test environment.

Further policy/ordering laws cover source-bound destinations, typed controller evidence, complete private-package/tag association, no push after failed qualification, tag substitution refusal, no rebuild after qualification, borrowed retention on success/failure, and close-failure terminal evidence. Cleanup negatives require exact recorded IDs and matching labels; unrecorded same-label objects must never be adopted. These tests use isolated doubles and cannot close native live acceptance.

Terminal diagnostic tests reuse the same producer command doubles to fail package/versions reads, controller acquisition, build, qualification, push and post-published-helper remote verification. They assert entered-stage/status, original exit preservation, no private canary and no later push when qualification or earlier work fails. Both success/failure with an unwritable diagnostic destination preserve their original exit and do not overwrite the destination. Pre-admission refusal produces no invented diagnostic. Synthetic success only exercises shell orchestration; it is not live publication evidence.
#225 adds contents-observation entrypoint admission targets: missing receipt
arguments refuse before Docker, valid tooling metadata reaches only the scripted
image admission boundary, and the observation-only result cannot satisfy the
existing package qualification evidence parser. Command doubles do not prove
an image, real helper, or provider effect.
