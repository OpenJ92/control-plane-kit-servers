# #163 explicit child image inputs — source validation

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

Released source-only validation passed at63645d0. Focused new-law tests cover incomplete/conflicting
inputs before fixture setup, all eight nodes' image/document joins and one shared
connector, original three waits/checks, four PostgreSQL-to-CPK edges and all three
ingress/runtime bindings, distinct connector IDs, every node's execution image
metadata, and the full/legacy environment boundary. Duplicate role AND nested
descriptor keys refuse in the new full JSON; legacy duplicate parsing is unchanged.
Existing PG-image/version, full companion, signer-lifetime and normal registration laws
are retained. Tests use explicitly synthetic `example.invalid` values only; they
never acquire or qualify an image. The Docker source-only suite compiled pure
synthetic graphs; no qualified real-image cohort was recompiled, and no provider
commissioning, submission or deployment ran.

Meridian's first review held the launcher boundary: although Python refused
before fixture/provider work, ordinary registrations allocated a network/PG and
the root gate built a controller first. Shared `http_sample_image_inputs` now
provides the same decoder to a preflight CLI. For the NEW full input only, the
root gate invokes it before policy/build stages; the ordinary source launcher
also invokes it before registration exports/network/PG. It requires an explicit
cached immutable `CPK_SOURCE_IMAGE_VALIDATOR`, exports exact Core054 source and
mounts this checkout's actual codec into one network-none/read-only controller.
Invalid input may start that isolated validator and create/remove public source
scratch files; it cannot build a controller, create the registration network or
start PostgreSQL. Valid input does not grant registration permission. Legacy
no-input/PG-only launcher behavior is retained.

The fake-CLI regression enters BOTH ordinary root and registration launchers,
runs the actual shared codec against the outer owning gate's pinned Core, and
requires refusal with only image-inspect/validation-controller calls. Docker and
Git archive transport are explicit external doubles; no Core state is faked.

Prepared minimal source-only action, ONLY after exact source review/release:

```sh
DOCKER_CONTEXT=desktop-linux \
CPK_SERVERS_TEST_IMAGE=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba \
./test.sh --http-sample-source-image-input-tests CORE_REPOSITORY OPERATIONS_REPOSITORY INTERPRETERS_REPOSITORY
```

The three repository paths must hold the existing pinned Core054e5884,
Operations71db67c5 and Interpreters2e2a6b88 Git objects. The owning launcher exports
those exact sources, uses the cached controller without build/pull, network none,
and mounts THIS checkout at `/source` ahead of stale `/app` scripts/product code.
It retains ordinary policy/support/integrity checks and runs all focused pure
assembly tests (including unchanged default/PG-only cases) plus launcher refusal.
No provider, registration network, PostgreSQL or API authoring runs in this phase.
Actual registration remains a separately released data-affecting action.
No host Python, build, acquisition or registration is part of this action.

## Owning source receipt — 63645d0

Meridian PASSed exact source/action
`63645d0813c0bf82bc3a81098b0cc6634ff12ba2`; North released one source-only run.
The initial sandbox invocation failed before Docker/tests with socket permission
denied. Its log remains `/private/tmp/cpk163-qualified-image-inputs-63645d0.log`,
SHA256 `c7f6ecaa6185d3a6d5acc0e023badc1588f5b50d070492d796b43917669dcb06`.
North separately released the identical command with approved host Docker access.
No effect was replayed and no automatic retry occurred.

That host-context invocation exited0: coordinate/integrity checks,28 support
tests and all8 focused tests passed (17.974s), including all default/PG-only laws
and both ordinary-launcher refusals. Public source exports were removed and the
owner emitted its cleanup success marker. Terminal log
`/private/tmp/cpk163-qualified-image-inputs-63645d0-host.log`, SHA256
`cecfbc138724e46215c564de363df8b35905a81a0e25e9b12b46c33d8baa248f`.
Core054e5884/Ops71db67c5/I2e2a6b88 exact exports and this checkout's mounted
source were used; the controller was borrowed by immutable ID. No real provider,
PostgreSQL, custom registration network, image build/pull or deployment ran.
This documentation-only receipt does not change tested source or qualify images.

Security/history: public image inputs only; no new route, permission, network or
credential surface. Pure selection performs no durable mutation. The normal
registration path's existing transaction/authorization/metadata/replay behavior
is unchanged and was not executed. Actual approval, effects and structured run
history remain with their current owners; no runnable plan or successful
deployment is claimed until qualified inputs, owning validation and normal
planning/execution evidence exist.
