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

The existing optional pair currently adds artifact ABI smoke checks. Its later
root launcher still uses historical canonical images; it does not yet run fresh
dynamic initialization/enrollment against the optional pair. #347's reviewed
source and HTTP/PostgreSQL component results do not close that gap, and full
dynamic apply remains guarded.

The planned extension reuses `test.sh` and `live_root_bootstrap.py` for one
additional isolated dynamic case. It keeps the mandatory historical static case,
existing tuple admission, native PostgreSQL selection and exact-owned cleanup.
The current pair needs actual source-owned CPK/Secrets runtime contracts and
commissioning artifacts, not the historical fixture's inert file witness. It
must exercise ordinary `bootstrap.sh plan/apply`, private initialization,
authenticated public enrollment, retained policy custody and actual process
restart with revoked permissions still revoked. No direct store grants or
private deployment call may substitute for the public path.

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
