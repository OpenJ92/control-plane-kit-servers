Source: [products/postgres_server/Dockerfile](../../../../products/postgres_server/Dockerfile).
Maintain this companion alongside its source and selected dependencies.

For #341, the unchanged coordinate generator renders this recipe's existing
dependency subset from the accepted Core/Operations `4cc1716b`, Interpreters
`bd08b931`, SDK `464df26c`, Secrets `067678fb` cohort. Full hashes live in
the canonical manifest. Extras, base images, process behavior and published
identities stay unchanged. The released owning-gate retry is pending.

The PostgreSQL source recipe retains its exact base image, installs Python and
the SDK verification extra, copies its product-owned process wrapper, and runs
as UID/GID 70 with the existing database and control ports. File-based password
and wrapper-configuration inputs remain deployment-owned; no credential is baked
into this recipe.

For #313, the existing coordinate generator updates only the SDK archive URL to
accepted merge `43838fd0f4391428cfffa87f8c4dbd5cc6d5eab1`, which selects accepted
Core `879efb9576ac0580a6236d0a7372c036537b4dfe`. Base image, package subset, user,
environment, entrypoint and ports are unchanged. The normal source-product gate
must prove build/composition compatibility; this recipe edit does not publish an
image or change historical product source/tag/digest/descriptor coordinates.


## #349 aligned Components dependency cohort

Current generated dependencies and provenance expectations follow accepted
Core/Operations fec0816, SDK cd4722f, Secrets 46e0718 and Interpreters 27457ca
in `coordinates/server-products.json`. Predicates, extras, runtime behavior and
historical product identities are unchanged. The canonical coordinate companion
records the resolved packaging blocker; the owning Servers gate remains pending.
## Current #351 dependency selection

#351 advances this source's existing dependency/provenance surface through
`coordinates/server-products.json`: Core/Operations 7afef43, SDK 220f631,
Secrets a3ca963, Interpreters 71ab335. These are actual accepted owner merges.
The canonical manifest carries full commits. Existing extras, runner, provenance
predicates and published product/image/catalogue identities are preserved.
Earlier cohort accounts below are historical. This checkpoint awaits the owning
Servers gate; pin selection alone is not installed or live acceptance.
