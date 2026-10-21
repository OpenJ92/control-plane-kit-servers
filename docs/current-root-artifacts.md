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
