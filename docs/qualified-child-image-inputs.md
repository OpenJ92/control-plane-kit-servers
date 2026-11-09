# #163 explicit child image inputs — unexecuted source preparation

The earlier complete assembly accepted an explicit PostgreSQL image only. Its
other product documents retained fixture/catalogue defaults. A qualified Secrets
or CPK image existing locally did not select it into that graph.

The existing source fixture now accepts `assemble(images=images, ...)`, where
`images` is one dictionary of six actual Core `OciImageReference` values with
exact keys `cpk`, `postgres`, `secrets`, `website`, `gateway`, `connector`.
The existing Core image codec validates the values. Missing/unknown roles, null
or string values and conflicting full/legacy selection refuse before fixture
setup. No new descriptor, registry, framework or qualification model is added.

Before composing the baseline or full graph, ordinary product descriptor
replacement selects CPK/PostgreSQL/Secrets images. The existing management and
website inputs select gateway/website images, and one connector document is
shared by API, website and management ingress. Gateway's later HTTP-sample
descriptor extension preserves that selected gateway image. Normal product
documents and graph metadata therefore carry the selected references together.

Both existing pure assembly and normal registration/authoring fixture entrypoints
accept `CPK_SOURCE_ASSEMBLY_IMAGES`: JSON mapping those exact six role names to
the existing Core OCI image descriptor objects, including their normal platform
and provenance fields. `image_options` decodes this before any commissioning
fixture/provider/API work. The owning source launcher forwards that public input.
The registration path keeps its same once-assembled graph and product documents,
normal imports, real version commissioning, exact stored graph/readback/replay
checks. No direct store mutation or deployment command is introduced.

Legacy `assemble()` and `CPK_SOURCE_ASSEMBLY_POSTGRES_IMAGE` callers remain valid;
the legacy image plus explicit versions still follows its old PG-only boundary.
Supplying both image environment inputs, or both `images` and `postgres_image`,
refuses instead of inventing precedence. Legacy fixtures are not relabeled as
complete runnable installations merely because the new option exists.

Known isolated child Secrets acceptance is
`localhost/control-plane-kit-servers/secrets-server@sha256:0d36584018d93305045631a1ee981d5a8850e16fd4532d765eb43a1a823dc095`,
[accepted by North](https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-6746498542).
This document creates no filled six-role run input. The real gateway digest is
pending its independent packaged qualification; do not insert a placeholder or
borrow a synthetic unit-test digest. Every eventual role needs its exact accepted
image/evidence and normal reviewed input. Image syntax is not qualification.

Validation is PENDING. Three focused new-law tests cover incomplete/conflicting
inputs before fixture setup, all eight nodes' image/document joins and one shared
connector, original three waits/checks, four PostgreSQL-to-CPK edges and all three
ingress/runtime bindings, and the full/legacy environment boundary. Existing
PG-image/version, full companion, signer-lifetime and normal registration laws
are retained. Tests use explicitly synthetic `example.invalid` values only; they
never acquire or qualify an image. No Docker, source recompile, provider
commissioning, submission or deployment ran for this candidate.

Next validation belongs to the existing Docker-backed owning source assembly
selector, with the exact reviewed source cohort and normal discovery of
`http_sample_installation_tests`; registration validation is a separate released
data-affecting action. No new gate, host Python, controller build or automatic
retry is proposed. `git diff --check` is the sole completed source check.

Security/history: public image inputs only; no new route, permission, network or
credential surface. Pure selection performs no durable mutation. The normal
registration path's existing transaction/authorization/metadata/replay behavior
is unchanged and was not executed. Actual approval, effects and structured run
history remain with their current owners; no runnable plan or successful
deployment is claimed until qualified inputs, owning validation and normal
planning/execution evidence exist.
