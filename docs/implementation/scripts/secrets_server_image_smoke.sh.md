Source: [secrets_server_image_smoke.sh](../../../scripts/secrets_server_image_smoke.sh).
Maintain with the owning product recipe, fixture and image profiles.

#384 wrapped-parent reuses the focused child owner, default entry, custody,
restart, signed checks and cleanup. Its parent-only derived recipe uses the
retained child0d365 via the shared bounded local OCI validator a9872bd, exact
UID10006/entrypoint/command and base-layer prefix. Parent fixtures exercise two
actual imported HTTP signer roles before/after restart; negative role/workspace
writes/resolves and unsupported/ungranted generation are mandatory. Only public
version/status evidence is retained. Normal child recipe/coordinates/digest are
unchanged. Source/action packet is [here](../../parent-secrets-image.md), still
UNEXECUTED; no qualified parent digest or active grants are claimed.

Parent source selection now requires an explicit local repository holding57,
archives only its17 package files plus pyproject.toml/README.md with a64MiB
bound and preserves commit/tree/blob identities. Two generated provenance files
complete the21-file named context; the operator receives its exact inventory.
The build receives this as a separate named local context, with no
Secret-package URL fetch. Public source scratch joins only the NEW attempt's
checked cleanup; previous receipts/scratch are never adopted or removed.

#191 adds wrapped-artifact/build0/controller-build0 for the explicitly selected
current digest. Existing public-file factories, signed reads, provider storage and
restart checks are reused. The selected process is pinned to the admitted actual
image ID with pull disabled; both initial and restart container Image/cache and
actual installed direct_url provenance are checked through the existing controller.
Two bounded public evidence/status files join the existing private fixture cleanup.

The existing finish owner now captures every container/volume/network inventory
status, removes only its run-labelled observations, and requires fresh successful
absence inventories. Removal/inventory/residue failures aggregate without retries.
Private-file cleanup must also succeed. Final smoke PASS moves from the body to
this finish boundary and appears only for primary+cleanup success; selected ABI
PASS follows it. Input images are never deleted. This fixes false-success reporting
in all existing profiles without a new cleanup framework. Source/default CI still
does not qualify an unexecuted selected pair or any live #225 behavior.

#204 restores default wrapped-source build. Profile/build flags and historical
immutable-image syntax are validated before Docker, directories or traps.
Explicit legacy BUILD_IMAGE=0 selects published-baseline; contradictory inputs
cannot substitute another successful mode.

Original private/bootstrap/data setup, write/generate/replay/resolve/revoke and
retained-value restart assertions remain. Provider creation is separate from
start so its labelled resource exists first. Source mode generates a public
artifact and purpose-separated headers before each startup, after builds; checks
run immediately after readiness. Stable synthetic target/runtime uses fresh keys
and120-second tokens per phase. No signing key persists or denied token refreshes.
Historical mode creates no source authority or new receiving/image evidence.

One host-owned0700 root holds initial/restart directories. Generation uses the
host UID/GID and network-disabled controller; control.json is0444 and headers0600.
Provider mounts only control.json read-only at the recipe ENV path. Root check/log
controllers use read-only mounts without a daemon socket; only HTTP checks use
the provider network.

Both profiles capture all logs through a1048577-byte limiter into fixed0600
provider.log; separate0600 log.status records producer exit status. Consumer
failure, failed/missing producer status or capture exceeding1048576 bytes fails.
The helper checks old markers/exact private values and source tokens without
matching output or token argv. Capture does not create a hard Docker deadline.
HTTP has bounded accumulation and per-operation timeouts, not a total deadline.

Finish retains labelled Docker cleanup and namespace audit, then deletes named
root log/artifact evidence files and three files per known phase. Partial generation/check
failure follows the same path. Unknown files or failed removal prevent rmdir
and retain the recorded path; no recursive prune or foreign-resource cleanup.
The first full owner run passed both profiles, including initial/restart signed
source reads and original custody/retained-value checks. Source success cannot
substitute for published qualification or public grandparent acceptance.
The selected artifact verifier requires actual PID 1 effective UID 10006 on both
initial and restarted provider containers. Bounded private status/exit records
join exact fixture cleanup; only validated role/PID/UID reaches public output.

#354 makes fixture seed intents explicit for accepted E: write is limited to
`postgres.password`, the existing application-value write; delegated signing
continues through the separately scoped generation grant. Revoke explicitly
uses an empty intent list because it is intentless. Resolve/generation scopes,
all storage/restart/denial assertions and published-baseline execution remain
unchanged. No admin capability, new workspace or wildcard authority is added.

#386 keeps the initial source phase without a companion and opts in only the
source restart. The bounded witness prepares public trust before restart, waits
for the existing actual readiness signal, mints one15-second grant and reads
once through secrets-provider:8081. Inner correlated PASSED/status200 and exit0
are required. Existing run-labelled cleanup/absence covers the helper; exact
public marker files join existing phase cleanup. Private keys stay in memory.
Published profiles and retained-custody assertions remain unchanged.

Review correction: after readiness the parent polls helper completion for at
most20seconds, requires authoritative exited/status0, and fails into the normal
owned cleanup on timeout/inspection failure; no unbounded docker wait remains.

## Servers #163 focused child Secrets action

Source preparation only. Read the frozen checkpoint's exact command and obtain
Meridian/North review/release before any Docker command, including its tests.
The product source, Dockerfile and entrypoint remain byte-identical to reviewed
85b193bbdc777376c5104029a5ee04e74627cf71. The existing recipe selects Secrets
158b17ed10689360c4e1529a395b3ee2b47aecbc, whose pyproject selects Core
976901c609d950a557ec1e9966f018e8ff6e16aa and SDK
d61b374cb2a23d773c31748f47f88169499298b7. No dependency change is proposed.

The source trace at that Secrets revision is: product entrypoint execs the
unchanged uvicorn factory; product server:create_app reads the independent
public control/optional HTTP companion before application.app_from_environment;
the service composes API authentication and admit_provider_custody over its own
native SQLite path, master key, provider ID and seed credentials. The custody
owner verifies/initializes its binding and encrypted store. Authenticated client
write/resolve/generate/replay/revoke use that real HTTP service. Replacing the
process against the SAME bootstrap/master/data volumes re-enters custody
admission; explicit version resolution and a private value comparison prove
continuity. No host database, fake store or Operations history is introduced.

The smallest missing packaged connection was the maintained smoke's ready-only
sample and absent focused selector/provenance receipt. Existing restart checks
resolved latest and tested revocation only before restart. This action uses the
same owner flow, adds exact written-version resolution before/after replacement
and explicitly checks the revoked version after replacement. The evidence is
kept separate from signed receiver checks and cleanup.

After exact-head review/release, run from that clean committed checkout:

```sh
export DOCKER_CONTEXT=desktop-linux
export CPK_SERVERS_TEST_IMAGE=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba
export CPK_RECEIVER_DAEMON_ID=d23d00aa-b281-448d-bc95-c8e47efeeea2
./test.sh --secrets-packaged tests

CPK_SECRETS_IMAGE=localhost/control-plane-kit-servers/secrets-server:cpk163-receiver-20261109-01 \
CPK_SECRETS_CHILD_RUN=cpk-secrets-image-smoke-cpk163-20261109-01 \
CPK_SECRETS_CHILD_RECORDS=/private/tmp/cpk-secrets-image-smoke-cpk163-20261109-01 \
./test.sh --secrets-packaged image
```

Tests must pass before image mode. They retain policy/support/integrity checks
and discover the maintained Secrets unit tests, including the new refusal,
reservation-ownership and exclusive-bootstrap cases. Focused source tests are
not packaged acceptance. Controller/daemon absence or mismatch stops; do not
build another controller or repair/acquire prerequisites implicitly.

Image mode performs ONE local linux/amd64 build from a clean tracked Git archive,
with the exact local-context builder. Permitted acquisitions are only the
unchanged public recipe's python:3.12-slim base, public pinned Secrets/Core/SDK
archives and normal PyPI dependencies (including cryptography50 and uvicorn).
No registry credentials, protected files or user credential environment values
are passed to the build. It records actual build metadata and local RepoDigest,
requires the exact reference to resolve to the built execution ID, checks
installed direct-URL origins/import/pip consistency inside that image, and
retains the image. No registry push, catalogue update or CPK rebuild occurs.

The canonical fresh `/tmp/<run>` directory reserves the run after successful
source/daemon/controller/tag/name/label inventories. A fresh32-byte nonsecret
owner identity is read from OS randomness and attached to each allocation.
Existing volumes must not be adopted just because they have the public run
label. Every volume is verified for exact name, run+reservation owner, local
scope/driver and no driver options immediately after create and again before
seed mounting. Wrong ownership or failed readback stops without bootstrap or
foreign removal. The seed opens all three directories without following links,
requires empty contents, creates each fixed credential/master path exclusively
with no-follow, verifies only its expected files exist and sets exact private
modes/owners. It never rewrites an existing credential or custody file.

Fixtures: one internal network; three owned native local volumes (provider
bootstrap, client bootstrap, encrypted data); one exclusive bootstrap process;
one provider on each of two sequential startups using the same image/storage;
one initial and one restart in-memory sample helper; and short-lived named,
tracked controllers for provenance, public-control generation, readiness,
protected reads, custody clients and redaction checks. No Docker socket or host
port is mounted/published. Networked reads use secrets-provider:8081; generation,
bootstrap, provenance and log checks have no network. All run/cid/owner checks
and exact cleanup remain within this run; images are retained.

Rowan's public tuple is root-workspace / root-a-docker / root-a-secrets / control
on8081. Each public artifact is0444 at the product-owned control/sample slot.
The service-owned generic V2 declaration stays liveness-only; named HTTP live
AND ready use their original paths, policies and check digests. On each startup,
after actual readiness and image/default-entrypoint/PID1 UID10006 checks, one
still-running synthetic sample signer proves BOTH original checks with distinct
requests and ordinal1. Each also requires absent401 and same-key validly signed
foreign-issuer401. The sampler must exit0 within45polls. Results are copied to
separate initial/restart public receipts BEFORE later custody operations, so a
custody failure cannot suppress completed signed observations. A failed phase
stops the action; not-reached stages remain not reached. Overall acceptance
requires every stage, both full pairs, redaction and cleanup to pass.

Provider authentication/private custody remain the original synthetic scoped
workspace-image-smoke seed and provider ID control-plane-kit, distinct from the
public child receiver tuple. Fresh phase receiver trust does not reinitialize
the private custody volumes. Initial write records only public version IDs and
numbers, resolves that exact version and compares material privately. After
FORCED container removal and replacement, the same version is resolved/compared,
and the separately recorded revoked delegation version must return REVOKED.
Only bounded public metadata/booleans are retained. No graceful-stop claim, real
application password, installed-child authority or approved run is earned.

Cleanup removes only recorded attempted container roles with matching cid/name,
run AND reservation owner, exact verified unreferenced volumes and the verified
network. Unexpected objects sharing a public run label are left untouched and
make cleanup fail. Every inventory/absence query must succeed. Known private
header deletion is attempted for both phases independently before other file
cleanup. Unknown residue/failed reads/deletion remain unverified; no repeated
removal, broad prune, silent retry, credential repair or rebaseline. The final
receipt separates installed provenance, initial custody, retained exact-version
retrieval/revocation, each signed phase, logs, cleanup and candidate retention.
CLI polling assumes responsive Docker; apparatus failure is a stop.

Gateway relay remains Rowan's owner and a later distinct effect boundary. This
action exports no private signer, gateway transit token or workload credential.
The custody test's legacy gateway-probe key is synthetic provider evidence,
not the gateway HTTP transit or workload-sample signer. Return the actual Secrets
RepoDigest and public receiving/check coordinates for Rowan/North routing; a
later gateway test creates its own fresh live fixture receiver/trust. No provider
transit, parent installation, deployed SQL wait or approved durable run/history
is claimed here.
