Source: [cpk_server_image_smoke.sh](../../../scripts/cpk_server_image_smoke.sh).
Maintain with the owning smoke profiles and local synthetic effect plan.

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
