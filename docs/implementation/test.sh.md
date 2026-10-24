Source: [test.sh](../../test.sh).
Maintain with the normal Docker-backed owning gate and prerequisite effects.

#191 adds explicit PostgreSQL source-test and published-image routes through
`scripts/postgres_artifact_shell.sh`. The latter borrows an already-present exact
digest and reuses the existing product witness. It requires separate runtime
authorization and is never selected by default CI. See
[managed PostgreSQL artifacts](../managed-postgres-artifacts.md).

#306 adds one unconditional representation regression after the existing
controller/package/import checks and before product runtime effects. It calls
the actual sourced `root_artifact_inspection` function on the cached `hello_family`
image selected by the existing fixed-input manifest, using Docker's real renderer.
The existing preloader independently verifies that image's identity and revision
label. Its inspected ID is distinct from the already-built validator controller
ID; the inspected product is never started. No extra image pull/build is added.
Capture preserves producer status
and caps output at 65537 bytes, requiring success and at most 65536 bytes.
The existing controller parses through the bounded reader and validates the exact
outer/Config/Labels whitelist, types and observed image ID. The schema still
allows empty user, absent revision and null RepoDigests; the selected fixture
has the revision label required by the existing preloader.

The validator has no network, daemon or credentials, uses a read-only root and
private evidence mount, drops capabilities and runs as the invoking numeric
UID/GID. It prints no raw inspection data. Fixed capture, producer/status, size,
parse and contract failure markers distinguish the boundary without exposing
inputs. Exact output/status file and
directory cleanup gates the sole success marker; cleanup uncertainty fails.
No new workflow, helper harness, image build or product effect is introduced.
At the test-only checkpoint the malformed source template is intentionally
preserved for causal red; all 944 package methods and 23 artifact/UID targets
remain unchanged. This regression is not actual-pair qualification evidence.

#191 additionally admits `CPK_ROOT_ARTIFACT_MODE=published-digest` with exact
CPK/Secrets references and producer revision. Default mode refuses populated
optional fields; invalid tuples refuse before Docker. Mandatory source builds
and historical invocations remain literal and unchanged. Additional wrapped-
artifact calls follow those paths, using the existing controller without rebuild.
Gate and producer revisions are distinct; independent cohort/recipe equivalence
remains required. Later root/connector/PostgreSQL/final residue stages remain.
Source green cannot qualify an unexecuted pair. See [selection](../current-root-artifacts.md).

Servers #279 tightens only the PostgreSQL source witness's retained-data start
sequencing. On the existing restart, recovery predecessor and recovered
successor paths, the already attached controller first observes the container's
native TCP 5432 listener and then runs the unchanged exact retained-row SQL
proof. Listener attempts, backoff and SQL polling share one deadline; every
connect timeout and sleep is capped by its remaining budget, container terminal
state is checked before listener attempts and before each SQL exec, and every
successful observation socket is closed. The initialization path and its
UNKNOWN-before-row evidence stay unchanged. This ordering check does not remove
or rewrite PostgreSQL locks or data, add a network, retry a lifecycle action, or
replace the exact SQL exit/stdout/stderr proof.

Servers #228 adds scripts/cloudflared_connection_witness.sh before the final
residue audit. It builds the source connector and checks packaged reader output,
numeric UID, synthetic token permissions and effective image configuration in
an isolated network-none fixture. Original published product stages remain;
no tunnel, provider credential or image publication is involved. See the script
companion for exact owned cleanup and the limits of signal-path evidence.

Servers200 changes only the source CPK smoke invocation to explicit wrapped-source
and passes the just-built existing test/controller image. It owns no alternative
harness. That source smoke now creates bounded synthetic receiving files/grants
as documented in its companion; the canonical published/root and numeric probe
paths retain their existing distinct purposes. Numeric file proof invokes its
explicit probe command, not the newly required receiver's main entrypoint.

A gate release must name the source fixture's generator image, files/mounts,
240-second grants, bounded requests and exact cleanup as well as the existing
policy/package/image/Secrets/restart/root/reapply/residue effects. Source smoke
success cannot substitute for qualification, artifact delivery or public acceptance.

The source-profile/test-image assignments precede the literal forced-build
CPK_SERVER_BUILD_IMAGE=1 sh invocation, preserving the shared gate-policy law
that ambient build-disabling inputs cannot skip the source image build.

#204 adds a forced Secrets wrapped-source smoke before its existing canonical
historical smoke; both profiles run through the maintained script. The source
tag can be set with CPK_SECRETS_SOURCE_IMAGE. Both share the already-built owner
controller image, without another controller build or daemon authority. The
source stage adds initial/restart public configuration and private headers;
both modes use bounded private log capture, independent producer-status checking
and exact file cleanup. The full release must include both complete custody/
restart runs and source build, not merely package tests. Existing numeric, CPK,
root and final residue stages remain. No new publication or public acceptance.

#191 always builds current Hello and gateway images alongside the existing
numeric-bootstrap source inputs. Their run-labelled IDs enter the same isolated
controller and exact cleanup ledger for current V2 artifact socket qualification.
No publication is required for this source gate and no new law is silently skipped.

After separately authorized publication and producer-side preload on this SAME
daemon, `CPK_WRAPPER_ARTIFACT_MODE=published-digest` additionally requires
`CPK_WRAPPER_HELLO_A`, `CPK_WRAPPER_HELLO_B`, and `CPK_WRAPPER_GATEWAY`, each an exact
private GHCR digest reference. The ordinary `./test.sh` still runs its source checks
and all existing later phases; the identical artifact routine then qualifies A/B
and the gateway with real RepoDigest/ID/linux-amd64 checks. Missing inputs/cache or
an unsupported mode fail, with no login/pull fallback. This mode is required before
#251 and is not a substitute for its CPK-driven scenario. Source-built platform
observations alone are not the published linux/amd64 qualification.

The controller never mounts host Docker credentials and creates its own private
empty Docker configuration. Existing host-side package-read login remains available
to unrelated established private-image phases. The socket grants daemon authority,
not resource-scoped authority; fixture code must remain confined to the exact owned
resource ledger. No provider credentials or original tunnel/DNS/token are involved.

The existing `tests.yml` manual dispatch now exposes the explicit artifact mode
and three digest inputs. PR/push validation always selects source-built mode.
Published mode uses the existing host packages-read login, validates all inputs
against exact product repositories/canonical digests before any pull, requires a
Linux/amd64 daemon, pulls each reviewed digest once, and inspects platform,
RepoDigests and image ID. Preload and the unchanged full gate share one job/daemon;
this does not populate a later #251 job's daemon. Inputs enter shell through quoted
environment variables, never expression interpolation into shell code.

The published dispatch needs its own exact-commit/tuple release. Recheck private
visibility and no active same-ref gate before dispatch because the existing
concurrency policy cancels matching runs. Compare observed artifact IDs with the
recorded publisher build IDs and correlate controller/preload daemon IDs. A failed
pull, access check, platform/digest check or ambiguous result stops the run; no
visibility change, credential expansion or automatic retry is authorized.

#272 removes the added #264 counter OCI build, tag, image ID, controller input
and matching cleanup record. The required Hello/gateway source builds and
#269's two declarations on the same Hello image remain in the ordinary gate.
Their exact identity/owner checks, SDK helper ledger and final residue checks
are unchanged. Original generic SDK process examples remain covered by the
existing CPK smoke. This source cleanup neither removes a published image nor
proves the coupled #254 update; publisher retirement belongs to #271.
# Managed cloudflared package lane (#284)

The unconditional scripts/cloudflared_managed_witness.sh invocation remains after
the historical connector witness. The approved #284 split uses one exact managed
image for credential-free contents inspection and preserved controlled stop/fatal
cases. Success explicitly says package pass and live qualification pending.
The unsupported offline positive-native orchestration is retired; all real native
laws remain mandatory through later CPK/Cloudflare acceptance on #284. No skip,
flag, workflow or test.sh source change is introduced. Later PostgreSQL and final
residue stages remain required. Exact source review and the owning Docker green
are pending; causal target-red39451603339 is not whole-package acceptance.

## Narrow managed release validation

Explicit `--managed-connector-controller`, `--managed-connector-release-tests`, and `--managed-connector-candidate` routes exit before root artifact/policy/full-suite setup. Candidate mode uses the existing managed witness owner. Focused release tests run in the exact previously acquired Dockerfile.test controller with no socket/network and a test-only executable tmpfs for command doubles. All other isolation flags remain; this is not a product mount/configuration. Every acquisition/validation uses a new retained receipt directory; image identities and controller provenance are explicit. Default full gate and its managed witness behavior remain unchanged.
