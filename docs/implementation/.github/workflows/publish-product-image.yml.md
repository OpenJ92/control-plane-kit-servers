Source: [publish-product-image.yml](../../../../.github/workflows/publish-product-image.yml).

The optional inspect_cpk_accounts input defaults false and refuses non-CPK
products before login/publication. When explicitly selected by a joint release,
the job selects ubuntu-24.04 (its actual image version remains observed provenance)
and checkout disables persisted Git credentials. Other publication modes retain
their existing runner label and checkout behavior. For this opt-in mode,
the producer's existing policy-image override selects the pinned immutable Python
image; the later account step borrows that verified cache ID without acquisition.
Default publication behavior and the existing managed-product path remain.

Publication and inspection have separate named outcomes. Actual public root
reference/source/image-ID outputs are emitted only after the producer's push and
immutable readback. The account entrypoint cannot publish. Its failure leaves the
successful publication visible; no retry, rollback or overwrite is attempted.
This same job has packages-write authority; no token downscoping is claimed.
Both metadata and offline containers bind only the exact reviewed projection
script, never the checkout or its .git directory; job credentials are not mounted.

Only allowlisted status/provenance files are retained on failed inspection.
The candidate seal is uploaded only after the account step, including exact
owned cleanup, succeeds. Never upload credentials, raw diagnostics, image layers,
account files or whole private directories. The opt-in job has a 30-minute wall
limit, independent of its 600-second acquisition and 300-second offline phases.
Default jobs keep the standard 360-minute maximum. Producer pull/build storage
is outside the inspection quotas and remains a separate publication decision.

This is source wiring, not a dispatch or acceptance receipt. A concrete joint
release must identify final source, exact new tags, recipe/cohort/provenance,
actual produced references and the bounded inspection/cleanup actions. Existing
source CI cannot establish actual published-image account evidence.

The default-false typed `inspect_retained_cpk` input selects a separate
`inspect-retained-cpk` job and skips the entire `publish` job, including its managed
product path. This reuses the existing workflow registration; it does not replay
the producer. GitHub requires workflow_dispatch registration on the default branch,
so a new unregistered workflow file would introduce a separate release prerequisite.
The whole workflow is not read-only: only the diagnostic job explicitly overrides
permissions to contents-read/packages-read. Its checkout disables credential
persistence; it has no dependency on the publisher and no login/build/push/Secrets
step. Normal producer behavior remains selected when the new input is false.

The diagnostic job fixes the retained CPK337c8cf reference and producer94ecb34,
historical publication run40756067917/job123055193422. Product/tag inputs do not
select another diagnostic target. It passes the distinct exact diagnostic
GitHub revision to the existing entrypoint's retained mode. Both inspection
booleans are passed as data; retained=true with same-job=true stops in preparation
and cannot schedule publication. The entrypoint admits source, target and
prerequisites, records bounded initial status/provenance, then explicitly acquires
the fixed public Python controller. Preparation/pull failure does not fabricate a
candidate or cleanup; only the existing allowlisted public artifacts are uploaded.

The fixed controller pull uses disposable hosted Docker storage without an enforced
image-store quota, a separately accepted source/design exposure. Its300-second
CLI deadline plus15-second grace does not prove daemon work stops after timeout.
Existing3GiB target-acquisition and4GiB unpack phase limits are not a total job
storage cap. No retry, fallback or prune is authorized by a failed pull.
Execution still needs a concrete reviewed packet at the final source, naming
the diagnostic job and expected skipped publisher inventory. Source CI does not
authorize that attempt or establish the retained image's account evidence.
