Source: [publish-product-image.yml](../../../../.github/workflows/publish-product-image.yml).

The optional inspect_cpk_accounts input defaults false and refuses non-CPK
products before login/publication. When explicitly selected by a joint release,
the producer's existing policy-image override selects the pinned immutable Python
image; the later account step borrows that verified cache ID without acquisition.
Default publication behavior and the existing managed-product path remain.

Publication and inspection have separate named outcomes. Actual public root
reference/source/image-ID outputs are emitted only after the producer's push and
immutable readback. The account entrypoint cannot publish. Its failure leaves the
successful publication visible; no retry, rollback or overwrite is attempted.
This same job has packages-write authority; no token downscoping is claimed.

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
