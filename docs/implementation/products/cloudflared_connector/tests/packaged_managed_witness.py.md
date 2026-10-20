# Managed cloudflared package witness

Source: [packaged_managed_witness.py](../../../../../products/cloudflared_connector/tests/packaged_managed_witness.py).

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
f8215cc266744ef195a50a70d427c345da2acdbb (at least7 matching commit characters).
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
