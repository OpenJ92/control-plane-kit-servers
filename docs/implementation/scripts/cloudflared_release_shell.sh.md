# Managed release owner entries

All actual managed result paths now use the product-owned local volume helper.
The candidate controller writes a provisional cleanup=pending_volume receipt,
which cannot satisfy qualification. After controller exit, the shell validates
the exact admitted run/source/tree/controller/candidate association, verifies
candidate retention, removes the recorded empty unreferenced volume and fixed
scratch records, then atomically finalizes only cleanup=verified. Witness status
and diagnostics are preserved, including failure. Missing/mismatched receipts,
residue, failed removal or pre-rename interruption remain nonqualified. After a
completed rename, verified cleanup facts remain true despite caller interruption;
no effect is replayed. Acquisition and empty-volume records remain as private
supporting evidence. The finalizer owns this fixed invocation path, not an
arbitrary user-selected receipt. Publication still requires final pass/verified.

`--managed-connector-contents` is a separate diagnostic route. It validates the
same borrowed controller receipt/image association as focused tests, requires
clean current source, and records its commit/tree plus recipe/witness hashes.
It invokes the existing managed witness shell in contents-only mode and retains
private output, invocation exit and a closed cleanup/result record. This route
builds one current-source ephemeral managed fixture and observes only its helper
result channel. It does not claim current-source controller provenance or relax
candidate admission, and never publishes or qualifies an artifact. Default/full
candidate admission remains unchanged. A diagnostic failure remains nonzero.

The owning test.sh routes controller acquisition and focused release tests before broad setup. Acquisition builds only Dockerfile.test from clean source and retains source/tree/recipe/image/build receipts. Focused tests require an exact cached controller plus explicit receipt, mount current source read-only, receive no daemon socket, and cannot pull/build implicitly. They retain failure evidence and prove release behavior only, never managed OCI/live acceptance.

Focused dirty-source validation refuses untracked files: all participating new files must first be tracked (intent-to-add suffices). The retained commit plus binary diff therefore includes their contents. Earlier exploratory working-snapshot runs are not represented as reproducible committed-source proof. Candidate qualification requires a clean exact source and matched controller acquisition receipt.

Source-bound acquisition uses a retained `git archive` of the exact commit as Docker stdin context, with its hash and tracked/archive path-set comparison. Missing required inputs and submodules refuse before build; archive omission cannot silently produce an incomplete build. Narrow source-mounted modes refuse ignored executable Python, shell and native-module inputs in their participating roots, without deleting them; ordinary cache/report files remain allowed. `PYTHONDONTWRITEBYTECODE` alone does not prevent reading preexisting bytecode. The default gate is unchanged.

Scope: these checks belong only to this repository's owned controller/managed producer and narrow test lanes. The executable-input scan is limited to participating source/test roots (`products`, `scripts`, `src`, `tests`); unrelated ignored outputs are not a new repository policy. CPK consumers still treat OCI artifacts as opaque declared immutable images. Git does not determine all legitimate build inputs or prove transitive dependency reproducibility. These recipes currently COPY tracked local inputs; any future generated/extra input must be explicitly staged and identified by its producer rather than subjected to a generic CPK Git rule.
