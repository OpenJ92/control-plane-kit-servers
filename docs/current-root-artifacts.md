# Current CPK and Secrets artifact qualification

The ordinary `./test.sh` still builds current source images, runs their wrapped
tests, and separately checks historical published baselines. Those paths do not
qualify a later rebuilt image. The existing workflow's optional current-root pair
adds ABI checks through the same owners without replacing mandatory coverage.

| Workflow field | Meaning |
| --- | --- |
| `root_artifact_mode` | `published-digest`; default `source-built` adds nothing |
| `root_cpk_image` | Exact `ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:...` |
| `root_secrets_image` | Exact `ghcr.io/openj92/control-plane-kit-servers/secrets-server@sha256:...` |
| `root_source_revision` | Full reviewed common producer commit |

Shell equivalents are `CPK_ROOT_ARTIFACT_MODE`, `CPK_ROOT_CPK_IMAGE`,
`CPK_ROOT_SECRETS_IMAGE` and `CPK_ROOT_SOURCE_REVISION`. Partial inputs, unknown
modes, tags, wrong repositories or populated optional inputs in default mode
refuse. The first supported artifact platform is Linux/amd64.

## Before effects

The reviewed producer/preload/qualification packet records exact producer and
gate commits, private destinations and unique tags, dependency/recipe equivalence,
actual build/push outcome and immutable digest/ID/platform/user/source metadata.
Verify destination privacy, tag absence and no active same-ref gate before the
released operation; existing concurrency cancels matching jobs. The 30-minute
budget is unchanged. Do not blindly retry a timeout or ambiguous publication,
change registry visibility or expand credentials.

The existing CPK/Secrets producer branches require a clean checkout, build
Linux/amd64 with its revision label, and verify numeric users 10001/10006, platform
and revision before push. They capture actual image ID, recheck it after push
and select the exact repository digest. Metadata alone does not prove producer
review, registry privacy or ABI qualification. Other branches/catalogue remain.

When producer and gate revisions differ, independently compare canonical
coordinates, CPK/Secrets recipes, copied CPK/local-gateway source, Secrets
entrypoint and configuration/source-contract inputs. Harness/metadata changes
can be equivalent; runtime/recipe/cohort changes need an explicit disposition.
Caller inputs and image labels cannot establish that review.

## Selected evidence

The existing workflow validates the tuple before Docker access and preloads exact
references with its package-read credentials on the same daemon. It checks
platform, digest, revision and user. The fixed Hello/gateway input set is separate.

`wrapped-artifact` prohibits builds. It admits the cache reference, captures its
execution ID and starts that ID with pull disabled. Missing cache or identity
drift refuses. Reference/manifest digest is never equated with execution/config
ID. Actual container Image must match; the cache mapping is rechecked.

At CPK startup and both Secrets starts, a bounded read of `/proc/1/status` inside
the actual selected container must report effective UID 10001 or 10006,
respectively. This observes the running server, rather than the probe process's
default user. Missing, malformed, duplicate, oversized or wrong-UID observations
refuse. Raw status stays in private fixture evidence and is removed by its owner;
only the validated role, PID and effective UID are reported. No environment is read.

Probes read selected installed `direct_url.json` from the actual artifact. The
gate's immutable canonical cohort supplies exact URLs and subdirectories:
Core/Operations must select their own subdirectories; SDK/Interpreters/Secrets
cannot name an unexpected one. Package versions or controller metadata cannot
substitute. Output is bounded and contains only validated public fields. This
does not claim a complete reproducible third-party dependency lock.

Existing factories, signed purpose-separated reads, denial, process/storage and
Secrets restart checks exercise the pair. CPK's broader receiver/deployment
scenarios remain on the mandatory source path; no new state machine is added.
Only isolated test authority is used, with no host registry credential mount.

Secrets emits final success after successful run-scoped inventories, known-owned
cleanup, fresh absence observations and private-file cleanup. Failure remains
failure. CPK retains its authoritative residue audit; the whole-gate audit stays
last. Input images are retained. Producer/gate source, reference, execution ID
and platform are distinct evidence coordinates.

## Remaining live work

Source/default CI proves implementation/regressions, not an unexecuted pair.
Only the actual released pair through this gate earns artifact ABI acceptance.
Website/driver identities remain separate. Public reachability, mobile/browser
use, CPK-driven Hello deployment/edit/history and teardown belong to #225. No
tunnel, DNS, production key or retained root is changed by this source capability.

## Dynamic launcher boundary under #347

The final combined gate at `8bb96f9d60502e44e52b2f32c2f62e345cc91b3e` passed
[run40818456065](https://github.com/OpenJ92/control-plane-kit-servers/actions/runs/40818456065),
with [independent combined PASS](https://github.com/OpenJ92/control-plane-kit-servers/issues/347#issuecomment-6488312730).
It qualifies the following Linux/amd64 pair from common producer
`94ecb34d7d692c23a0ec017fdc0cac984fd9dccf`:

- CPK: `ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:337c8cf44d1ccf624663c866f8084655ead7e8f5c62c121424c9d15f7650e370`
- Secrets: `ghcr.io/openj92/control-plane-kit-servers/secrets-server@sha256:76439a4baf59b293ca54df12315efdd3e3b415ad98e35f5e0f11e88a02301415`

Both artifact ABIs, actual numeric process identities and selected dependency
provenance passed. The real dynamic launcher passed public enrollment, retained
policy custody, revoked-state persistence after restart, matching initialization
history and owned resource/private-file cleanup; the full suite's final residue
audit passed. The [terminal record](https://github.com/OpenJ92/control-plane-kit-servers/issues/347#issuecomment-6488288007)
distinguishes direct markers from mandatory source/control-flow inference for
repeated-apply refusal, driver removal and PostgreSQL source-stage completion.
This is isolated fresh-bootstrap acceptance, not retained/live adoption or #225.
The producer and tested gate remain distinct; later documentation does not
change those evidence coordinates. The following paragraphs retain the earlier
checkpoint history and its narrower evidence.

Source at `ac144857` adds the dynamic launcher described below and removes the
intermediate apply guard. Its complete default source gate passed in
[run 40738175098](https://github.com/OpenJ92/control-plane-kit-servers/actions/runs/40738175098),
including the seven synthetic account-projection laws. That run did not select
a current image pair or execute the offline unpacker. At that checkpoint only the
historical account baseline existed, so a new pair refused before dynamic
acquisition until its seal was reviewed. The subsequent reconciliation with
accepted #349 merge `fc4cd5b`
changed the dependency cohort; the final combined result above validates it.

The candidate extension reuses `test.sh` and `live_root_bootstrap.py` for one
additional isolated dynamic case. It keeps the mandatory historical static case,
existing tuple admission, native PostgreSQL selection and exact-owned cleanup.
The current pair needs actual source-owned CPK/Secrets runtime contracts and
commissioning artifacts, not the historical fixture's inert file witness. It
must exercise ordinary `bootstrap.sh plan/apply`, private initialization,
authenticated public enrollment, retained policy custody and actual process
restart with revoked permissions still revoked. No direct store grants or
private deployment call may substitute for the public path. It invokes the
existing `bootstrap.sh inspect-initialization` after restart to compare the
retained binding, then proves a repeated apply refuses without receipt changes.
Successful resource cleanup removes the fixture's credential/commissioning
directories; failures retain private diagnostic evidence. Borrowed images remain.

The existing numeric socket witness has an exact historical CPK image-account
baseline. Before extending it to another digest, review that image's independent
final-filesystem account evidence: repository digest, image/config correlation,
bounded passwd/group file hashes, UID, primary GID and supplementary groups.
Retain the historical baseline. Do not derive expected groups from the running
process or copy the historical baseline onto a new image. This account review
supplements the existing actual PID1 UID and dependency-provenance checks.

The producer and final launcher gate may have different reviewed source commits.
Record both and review every relevant difference before execution, including
which bootstrap modules the source-packaged driver actually selects. An image
label or successful source test is not evidence that a copied runtime change is
present in an older image. Publication, artifact ABI qualification and complete
dynamic launcher acceptance are distinct results. Exact producer destinations,
tags and revisions, then the resulting immutable pair and final gate revision,
belong in #347 before their respective released actions.

## Producer refresh after #349 integration

The proposed `25bf669a` producer and its proposed tags are superseded. Accepted
#349 selects Core/Operations `fec0816281aeb83ede98616adcc4f96dfe5777a8`, SDK
`cd4722fbfb942e7c2467a39b3cd0e32ded4a90ac`, Secrets
`46e0718664c425d002f2420a6ad1f996be62b2c5` and Interpreters
`27457ca5eab6ae96d78146e7ea0c998b986feab3`. Both product recipes now select that
aligned cohort. The earlier producer is therefore not equivalent to the combined
source, even though the ordinary server source files are unchanged.

Use the reviewed, owning-tested combined source as the new common producer.
Record its exact commit, unique private destination tags and recipe hashes in
#347 before publication release. After publication, the actual immutable pair
and independent account seal still precede a baseline update and the optional
current-pair gate. The original historical row remains separate. Acquisition
tool provenance, enforced acquisition storage/time limits, the exact offline
controller and owned failure cleanup remain explicit execution-packet
prerequisites; source CI does not supply them.

## Accepted current CPK account evidence

The later combined source and diagnostic corrections passed their owning gates;
exact95989d2 passed run40776581151. Retained CPK manifest337c8cf, produced at94ecb34,
then passed the separately approved actual diagnostic run40789512741. North
accepted [independent bounded account evidence](https://github.com/OpenJ92/control-plane-kit-servers/issues/347#issuecomment-6483769887),
with cleanup credit limited to that attempt and both earlier HOLD histories intact.

The test selector adds only that exact current-image account row while retaining
the historical row and unknown-reference refusal. It uses original configd300c4fb,
not normalized config51a42b83, with the independently observed account values.
The row alone is not live adoption or current-pair qualification. Secrets
publication at common94 and the separately released pair/launcher gate have now
completed, as bound by the exact references and independent review above.
Earlier failed diagnostics and launcher attempts retain their original limits;
later success does not establish their cleanup retrospectively.
## Current #351 dependency selection

#351 advances this source's existing dependency/provenance surface through
`coordinates/server-products.json`: Core/Operations 7afef43, SDK 220f631,
Secrets a3ca963, Interpreters 71ab335. These are actual accepted owner merges.
The canonical manifest carries full commits. Existing extras, runner, provenance
predicates and published product/image/catalogue identities are preserved.
Earlier cohort accounts below are historical. This checkpoint awaits the owning
Servers gate; pin selection alone is not installed or live acceptance.
