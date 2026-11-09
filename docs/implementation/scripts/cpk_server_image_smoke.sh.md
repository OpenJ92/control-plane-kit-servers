Source: [cpk_server_image_smoke.sh](../../../scripts/cpk_server_image_smoke.sh).
Maintain with the owning smoke profiles and local synthetic effect plan.

#225 admits Linux and Docker Desktop context-selected local Unix endpoints via
`docker_witness_daemon.sh`. Endpoint/TLS environment overrides are refused;
the resolved context is exported for subsequent CLI calls. The host client
socket path is not used as a daemon-host mount source: the controller still
mounts `/var/run/docker.sock`, and its existing daemon-ID/image/run-label checks
must succeed before workload effects. A nonempty CLI daemon ID is required.
Actual Desktop binding remains owning-gate evidence, not endpoint-string proof.

#191 adds explicit wrapped-artifact/build0 admission. The cached role-specific
digest, source/platform/user and actual execution ID are validated by the bounded
shared artifact owner before runtime effects. Selected image use disables pulling;
actual container Image/cache mapping and product-installed dependency provenance
are checked. Existing public factory/signed read/denial branches serve both wrapped
profiles. The broad receiver/image-update/reintroduction scenarios stay only on
mandatory wrapped-source. Historical baseline remains distinct.

Public provenance files join the existing fixture cleanup list. No CPK cleanup
rewrite occurs: its authoritative final residue audit remains unchanged, and
selected-artifact PASS follows it. Missing cache/build1 refuses; no registry
credential mount or production authority is added. Actual pair qualification is
separate from source/default CI and #225 public acceptance.

#255 runs the accepted image-update scenario followed by a separate
receiver-reintroduction scenario through the same finite Docker launch procedure.
Each controller has an exact distinct name and fresh record directory. Previous
cleanup must clear RECEIVER_RECORDS before another directory is allocated; each
ownership.json requires its own managed-resources-absent marker. Failure exits
through the existing preservation/cleanup path, never overwrites uncertain
records, and never advances to the next scenario. Image/dependency prerequisites,
Unix daemon check, controller image identity and final residue audit remain.

wrapped-source requires the existing test/controller image and the new source
receiver. published-baseline explicitly retains historical inputs and checks;
there is no runtime health-disable or fallback after source admission failure.
The source image still has only its src copied and runs UID10001 on8080.

After build/PostgreSQL readiness, create one mktemp directory0700 and invoke the
owned fixture generator in the test image with no network and host UID/GID.
Public control.json0444 is mounted alone, readonly, to the fixed receiving path;
UID10001 can read this public file. Separate0600 header files remain outside CPK.
First reject source startup with otherwise complete bootstrap but no control file.
Then run actual source and use curl header-file references (never token arguments),
connect timeout1s/request timeout3s/max response65,536 bytes. Require authenticated
static/liveness success, missing authority401 on both routes and wrong-purpose401.
An in-container no-network verifier checks response identity/declaration/outcome.
Legacy HTTP/MCP/readiness/history checks still run afterward.

Each grant lasts240 seconds from generation immediately before startup; no build
latency is charged to that window. Header/response files remain private via077
umask. Remove exactly control.json, surface.headers, health.headers, surface.json,
health.json and denied.json after container cleanup; rmdir proves the directory
empty/absent. EXIT/INT/TERM failure handling repeats exact cleanup as needed and
returns failure if new file cleanup fails. No broad prune, provider mutation,
credential refresh or unrelated cleanup is added. Existing diagnostic limitations
and ownership of the normal Docker effects remain unchanged.

The missing-control rejection probe uses a separately created, run-labelled/named
container whose exact ID is retained before start and included in existing cleanup.
At most15 one-second state inspections require exited/nonzero, then at most4096
bytes from the last10 log lines prove the fixed receiving error. If missing-file
enforcement regresses into a running server, the gate fails boundedly and cleans
the exact ID; it does not block in a foreground docker run or use a generic runner.

The15-poll bound assumes responsive Docker CLI calls; it is not a hard wall-clock
deadline against a hung daemon. Apparatus failure remains a stop condition.

Core #1912 adds one identified socket-free witness container only in wrapped-source,
using the maintained test image and this smoke's existing disposable PostgreSQL
network. A private cidfile, exact name and unique run label preserve allocation
identity across interruption. Cleanup verifies identity/ownership and absence;
no broad prune or implicit retry. The witness creates and drops isolated issue
schemas through real Operations bootstrap/UoW, leaving the source server schema
separate. Published-baseline does not invoke this source witness. The additional
container has no host listener, daemon mount or credentials from the user.

The witness cleanup function emits its bounded absence marker after successful
identity/label verification, removal, absence queries and cidfile-directory cleanup,
including on a failed witness path. Failure emits an incomplete-cleanup marker
with its retained record directory. Prior runs without these distinct markers
must not be retroactively described as separately verified absence evidence.

The #237 extension runs after #1912 in the same identified witness container with
`sh -e` failure propagation, ending in `exec` of the unlisted witness. It freezes
and later rechecks the controller image's immutable ID, mounts independent example
files read-only after build, and permits only container-local loopback listeners
and at most two tracked receiver children. No host ports or Docker socket are
added. Existing exact container cleanup runs for success, failure and interruption.

#251 adds a mandatory dedicated Docker witness after the socket-free receiver
and S1 witnesses. It uses the existing built test image/Postgres/network, exact
controller records and a local Unix daemon socket only in this controller. The
owned record directory carries the unique managed workspace and absence marker;
unverified cleanup preserves the records and fails. Fixed input preloading is
an explicit workflow prerequisite, not a scenario repair step.
The selected artifact verifier also requires actual PID 1 effective UID 10001
at startup. Its bounded private status/exit records are part of the existing
exact fixture cleanup; this does not replace Config.User or container identity checks.

#386 extends wrapped-source only with a bounded in-memory sample witness, a
source-only cpk-source network alias for the actual CPK listener, and the public
sample companion. After existing actual readiness, the shell signals the helper
to mint one fresh15-second grant and read once. Success requires correlated
inner PASSED/status200 and helper exit0. Exact owned helper identity/label and
absence are verified during cleanup. Published profiles remain unchanged.

Review correction: helper cleanup now uses captured full identity when known,
otherwise the exact name/run label. Each post-removal observation independently
checks status and emptiness. Helper uncertainty fails cleanup, preserves public
fixture records, and still runs independent receiver/CPK/Postgres/network cleanup.
Completion after readiness is parent-bounded to20seconds with observed exit0.

Final review correction: independently remove and verify absence of the two
owned bearer-header files before retaining public evidence on helper uncertainty.
Unlink/absence failure stays a fixed failed cleanup result; header contents are
never printed. Other independently owned runtime cleanup still runs first.

## Servers #163 focused packaged receiver action

This is an unvalidated source checkpoint. `wrapped-receiver` builds only the
CPK product, retaining the production source and Dockerfile byte-for-byte from
`85b193bbdc777376c5104029a5ee04e74627cf71`. It does not run broader deployment,
retained-connector, history or update scenarios. The unchanged product recipe
selects Core/Operations `976901c609d950a557ec1e9966f018e8ff6e16aa`,
Interpreters `e4bd35e828d1c44129f64e702de2b1d2b60f7c87`, and SDK
`d61b374cb2a23d773c31748f47f88169499298b7`. A normal install, installed-origin
inspection, `pip check` and actual default-entrypoint startup decide whether
that tuple works; no parent dependency upgrade is inferred.

Run from the clean committed selector checkout, only after Meridian's review
of that exact head and North's execution release. The `tests` phase must pass
before `image`. The source SHA is obtained from the frozen clean Git head;
tracked source is archived as the build context, and the head/clean state is
checked again after build and the witness. Proposed commands:

```sh
export DOCKER_CONTEXT=desktop-linux
export CPK_SERVERS_TEST_IMAGE=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba
export CPK_RECEIVER_DAEMON_ID=d23d00aa-b281-448d-bc95-c8e47efeeea2
./test.sh --cpk-receiver-packaged tests

CPK_SERVER_IMAGE=localhost/control-plane-kit-servers/cpk-server:cpk163-receiver-20261109-01 \
CPK_RECEIVER_RUN=cpk163-cpk-receiver-20261109-01 \
CPK_RECEIVER_RECORDS=/private/tmp/cpk163-cpk-receiver-20261109-01 \
CPK_RECEIVER_POSTGRES_IMAGE=docker.io/library/postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777 \
./test.sh --cpk-receiver-packaged image
```

The controller is borrowed by immutable ID from the existing reviewed source
controller build; it is never rebuilt. The context helper admits only a local
Unix endpoint with no endpoint/TLS overrides, checks the expected daemon ID,
and the build explicitly selects that context's builder. The exact PostgreSQL
fixture must already be cached. Availability has not yet been observed for this
checkpoint. Missing controller/fixture or apparatus failure stops the action;
there is no implicit pull, repair or retry. Any exact-digest prerequisite
acquisition needs its explicit release. The product build may acquire the
unchanged recipe's public `python:3.12-slim` base, pinned public GitHub archives
and ordinary PyPI dependencies. No credentials or private source are supplied.

The candidate is loaded locally as linux/amd64 with a run label and revision
label. The gate records the build artifact descriptor/digest and config digest
separately, and requires an actual matching local repository digest lookup.
A platform-manifest digest is recorded only when the observed descriptor is a
manifest. The main container uses that built image with its unmodified default
command; observed runtime image identity and PID 1 effective UID 10001 are
separate evidence. No registry push or installed-grandparent change occurs.

Fixtures comprise one internal run-labelled network, one run-labelled named
PostgreSQL data volume, one exact-digest PostgreSQL container, one sample helper,
one main CPK container, one missing-control negative, and four sequential
binding-refusal containers. Short-lived policy/test, provenance, control
configuration and response-verification containers use borrowed images with no
Docker socket; policy/tests/provenance/control generation have no network.
The product publishes only an ephemeral loopback port. All four database URLs
are forced to the same owned fixture, regardless of inherited operator values.
Runtime interpreters are explicitly disabled. No real provider call, credential
change or application workload is included.

A fresh synthetic public control artifact targets root-workspace / root-a-docker
/ root-a-cpk on http-api:8080. A separate sample signer remains in one helper's
memory for both original live and ready checks. The gate separately verifies:

- installed origins, dependency consistency and server import;
- actual default-entrypoint startup and non-root PID 1;
- four valid-but-mismatched database bindings each refused with the known
  same-instance configuration error;
- readiness reporting configured stores, plus an authenticated Operations
  workspace read returning exact 404 `missing workspace 'root-workspace'`;
- canonical signed PASSED/status200 samples for live and ready, distinct requests
  and ordinal one, with absent and validly signed foreign-issuer authority each
  refused with 401 for each check.

Readiness alone does not prove a database query. The workspace read exercises
the selected Operations shared store, not four independently observed SQL reads.
Fresh fixture identity/signers are not installed-child custody, an approved child
R/run/history, provider transit, gateway or capstone acceptance.

The canonical fresh `/tmp/<run>` directory atomically reserves the run. Existing
receipts, image tag, run-labelled containers or fixture names cause refusal.
Cleanup runs only after that reservation and only for attempted allocations,
using captured IDs/cidfiles or exact reserved-name recovery plus matching name
and run label. Every readback's exit status matters. Containers, the unreferenced
owned volume and network are removed with absence checks; private bearer files
are erased independently of uncertain helper cleanup. Candidate/controller/PG
images remain, with a final exact candidate digest lookup. No broad prune runs.

The public result keeps stage, exit code, source/daemon/controller correlation,
separate proof booleans, cleanup and candidate retention. First failure stops;
unknown ownership, mutation outcome, daemon change, absent prerequisite, source
change, image identity mismatch, import/pip failure, unexpected refusal/read or
sample result, and uncertain cleanup remain failed or uncertain. Do not retry,
rebaseline, change dependencies or claim qualification from partial evidence.
