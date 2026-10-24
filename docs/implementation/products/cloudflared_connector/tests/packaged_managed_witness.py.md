# Managed cloudflared package witness

Source: [packaged_managed_witness.py](../../../../../products/cloudflared_connector/tests/packaged_managed_witness.py).

## #313 current-source dependency adoption

The normal owning gate builds the current `Dockerfile.managed`, then mounts this
checker into that exact image. Its Core and SDK expectations therefore advance
to accepted `879efb9576ac0580a6236d0a7372c036537b4dfe` and
`43838fd0f4391428cfffa87f8c4dbd5cc6d5eab1`. Run 39998445394 installed those
dependencies successfully but failed this check's stale coordinates with
`installed_source_coordinate`, then `package_inspection_failed`. Managed-stage
acceptance, the later PostgreSQL witness and the final residue audit were not
reached. Earlier successful package and image stages do not make that run pass.

Only these two expected commit literals change. The existing commit-substring
predicate is unchanged; this does not strengthen it into exact URL or artifact
authentication. Native version, notice source `81a53555`, notice blobs, numeric
identity, controlled/fatal fixtures, deadlines and owned cleanup stay unchanged.
Selected-image qualification also uses this checker and requires clean source
HEAD, controller source/tree and candidate revision to match the selected source.
Older artifacts retain their original source/witness/controller cohort in Git;
no older artifact is newly qualified by this edit. Historical product
source/image/tag/digest records and earlier evidence below remain unchanged.
Normal owning validation of the correction is pending; no live proof is claimed.


## #291 provenance correction after mixed target red

The image-contents check now expects accepted Core `95566689` and SDK `cad5cc3d`,
matching the source recipe and SDK's declared Core dependency. Only those two
commit literals change. Native version, licenses, image profile, controlled
stop/fatal fixtures, deadlines and exact-owned cleanup remain unchanged.

The first #291 gate at `3fae9dd` passed 26 policy tests, root60, managed
connector80 and gateway61, then ran CPK478 with four failures: two intended
image-proof forwarding assertions and two stale current-composition pin checks.
It was not clean causal red. Later product/runtime/image and residue stages were
unreached. This bounded correction updates eleven current-source expectations
across four existing files; native targets and production forwarding are unchanged.
Independent correction review and a new owning run remain required. Full commits
are in the canonical manifest; earlier selections below remain historical.
No native live, image qualification or cleanup acceptance is inferred.

Servers #284 owns this unconditional stage of the existing Docker `test.sh`.
The approved issue law ledger separates source/package proof from mandatory real
Cloudflare acceptance through CPK after integration. #284/#188 remain open until
both lanes pass. This local implementation has not yet earned package green.

## Image inspection

The controller verifies the exact built image ID's original user65532:65532,
Python managed entrypoint, empty command, SIGTERM and healthcheck metadata before
any fixture override. One credential-free container from that image runs the
existing contents checker as PID1, with the default image user and network none.
Its healthcheck is disabled only on the fixture, as for controlled/fatal cases.
Only the readonly checker/notice manifest and owned writable results directory
are mounted. There is no token, SDK configuration, request credential or socket
in any image fixture. The controller alone retains the existing daemon socket.

Contents checks actual UID/GID before version I/O, the real native version,
selected Core/SDK source coordinates, exact103 notice blobs and dependency
license metadata. It does not launch a tunnel. The observation budget starts
before create, remains fixed at15seconds through start, terminal polling and
result consumption, and is checked around Docker calls. API timeout is temporarily
one second and restored in finally before the controlled stop. Finite API and
filesystem operations can overrun the deadline; no exact cancellation guarantee
is claimed. An actual exited State and integer ExitCode are required; a running
container's initial zero field never establishes success.

The inspector writes one exclusive result capped4096bytes, mode0400, owned by
65532. The controller uses NOFOLLOW/NONBLOCK, regular-file/owner/mode checks,
bounded read, stable size/timestamps, parsing/unlink and deadline checks. No
Docker archive or exec stream is used. Nonzero results always refuse as
package_inspection_failed; only a closed allowlisted failure record may enrich
that refusal. Missing/invalid/expired records never supply success, and a
failure envelope with exit zero refuses. Reasons and marker fields contain no
exception text, native output, configuration or credentials.

## Controlled process evidence

The same exact image and daemon run the preserved TERM-ignoring PID1 fixture.
The actual container/Engine/SDK profile is resolved from that container. SDK7.2.0,
Linux and SIGTERM are required. Timeout10 must be explicit or derived from the
reviewed fixed Unix default in Moby28.5.1 commit
f8215cc266744ef195a50a70d427c345da2acdbb or Moby28.0.4 commit
6430e49a55babd9b8f4d08e70ecb2b68900770fe (at least7 matching commit characters
paired with that exact version).
Unknown defaults refuse; no stop override is supplied. Moby source anchors are
container/container.go:597, container/container_unix.go:26 and daemon/stop.go:57.
This is compatibility evidence, not binary attestation.

Handler-ready/TERM receipts and the unchanged interpreter stop call are followed
by a finite exact-container event query. Integer timeNano and unambiguous
15/9/die137 require inclusive9–11seconds on the Engine clock. Initial start before
TERM is allowed; competing start/restart refuses. Controller clock continuity
is separately checked. The reported profile_container_id binds this evidence to
the controlled fixture, not a real connector. The preserved fatal-PID1 fixture
observes an owned child session, then SIGKILL and exited namespace/Pid0; it does
not scan host processes or prove graceful native shutdown.

## Failure and cleanup

Closed invocation-local markers use setup/artifact/profile/fatal/cleanup phases.
Created IDs are recorded before subsequent effects or deadline refusal. Primary
context is copied before cleanup, original failure takes precedence, all recorded
containers get cleanup attempts, and the client is closed. First cleanup failure
has a separate marker; cleanup-only failure refuses. Publication failures cannot
recover the original outcome. The shell's owner-label fallback covers uncertain
create outcomes without broad pruning.

The controller emits outcome=package_pass and live_qualification=pending only
after its container cleanup. Shell success additionally requires exact owned
container/image/fixture cleanup. Later PostgreSQL and global residue checks stay
mandatory. No success here proves normal native lifetime, token delivery,
current authority, bootstrap, authenticated management or real-native stop.

## Evidence and live handoff

Historical source e0402db preserves the retired offline normal-native witness.
Its synthetic-token/network-none profile has no native lifetime guarantee.
Runs39381573535,39384890071,39385659976,39389284324 remain failures with bounded
findings on #284; none establishes whole-stage or live acceptance. The final
historical observation was contents-helper137/result unavailable and subsequent
combined container exited1/Pid0, without a proved cause.

The package slice removes that orchestration and its now-unreferenced detached
exec, synthetic file/credential generators, HTTP/native identity helpers and
modes. Production coordinator/entrypoint tests and shared fixtures are untouched.
All positive native laws remain mandatory in the authoritative #284 live ledger;
they require independently approved real material, transport, selected runtime
profile and CPK actions. Protected grandparent ingress and paused #224 remain
unchanged. No provider action, credential change, dependency adoption or image
publication is part of this slice.

Target1a37e29 earned exact review, then gate39451603339 confirmed both intended
numeric-admission failures before actual version I/O. Nine other diagnostic
methods passed. That causal red does not establish this implementation's green;
exact source review and the released owning Docker gate remain necessary.

## Observed28.0.4 source-profile addition

Run39452982680 at f0d45fe passed all757 package methods and image contents, then
refused the actual Linux Engine28.0.4/build6430e49 with null configured timeout.
Controlled stop, fatal and whole-stage cleanup remained uncredited. Immutable
v28.0.4 resolves to6430e49a55babd9b8f4d08e70ecb2b68900770fe: container/container.go596
chooses explicit Config.StopTimeout or the Unix constant; container_unix.go26
sets10; daemon/stop.go55 uses that unless an explicit request override is supplied.
The HTTP stop route container_routes.go234 populates timeout only for a supplied
t parameter, and daemon/inspect.go89 returns the configured input. Null alone is
not an effective timeout claim. The signal-error branch at stop.go80 can shorten
its wait to2seconds; the unchanged empirical9–11second predicate still must pass.

Selected Interpreter2274d974 sdk.py1118 calls container.stop() without kwargs.
Docker-py7.2.0 immutable5ad5327fba623897ee9a527d7eee1b01703e0726 forwards those
kwargs at models/containers.py441; api/container.py1187 sends empty query params
for timeout=None. Its local10 extends HTTP timeout, not daemon stop timeout.
These immutable source anchors and observed advertised version/build justify the
closed pair addition, not binary attestation or measured stop behavior.

Targetd44b91c's owning run39458036934 produced exactly the two intended new
full/short28.0.4 positive-case refusals. Both reviewers accepted causal red.
The local resolver now selects one of the two exact version/source pairs; all
prefix-length, explicit integer10, Linux/SIGTERM/SDK and empirical laws remain.
Nonstring version values cannot enter map lookup. Source reporting returns the
matched immutable commit only for inferred defaults. No gate, dependency,
production code or runtime override changed. Exact source review and separately
released owning green remain necessary; all live laws remain pending.

## Pending #280 required-configuration adoption

The source checkpoint selects accepted Core/Operations `ec61e2b`, SDK
`eff0909`, Secrets `b30e626`, and Interpreters `2365565`; full immutable commits
are in the canonical coordinates manifest.
Dependency mirrors and current installed-source expectations advance together.
Earlier dependency/evidence accounts above remain historical. This checkpoint
is unvalidated: pin edits do not establish installed compatibility, image
qualification or live acceptance. Existing package subsets/extras, native/base
images, runtime/license inputs, assertion strength and published product
source/image/descriptor/catalogue identities remain unchanged. The existing
coordinate generator and Docker-backed owning gate must verify the prepared
source; no validation result is claimed here.

The existing `image_contents` predicate is commit-substring membership in the
installed `direct_url.json` URL. The new expected commits do not strengthen that
predicate into exact URL/subdirectory equality or artifact authentication.
Controlled-process package diagnostics remain distinct from the mandatory
connected-native/authenticated-receiver live laws under #284/#188.
