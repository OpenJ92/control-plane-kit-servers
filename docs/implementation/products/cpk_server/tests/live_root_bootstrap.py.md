Source: [live_root_bootstrap.py](../../../../../products/cpk_server/tests/live_root_bootstrap.py).

#301 extends the existing prepare stage with an offline commissioning witness
inside the actual bootstrap driver built by unchanged test.sh. A subprocess uses
only the image's CPK, gateway and Secrets product paths, checks product module
origins, prepares two isolated fixture keys, decodes both actual receiving
artifacts and verifies completed reuse. It emits one fixed public success line;
private output or caught child errors are not printed. Temporary fixture custody
is removed by its owning temporary-directory context and never enters ordinary
bootstrap material.

This is a source packaging witness, not production image qualification or new
receiver-protocol acceptance for the historical CPK/Secrets images. The existing
real launcher plan/apply/public setup, numeric identity/socket observation,
denial/no-redispatch and exact owned cleanup behavior is preserved. Historical
limitations in those observations remain unchanged.

SOURCE review found that the actual driver inherits the historical published CPK
image, not the current service Dockerfile. The witness now compares installed
Core/Operations/SDK/Interpreters/Secrets direct_url.json URLs and subdirectories
with the exact selected upstream manifest. Version 0.1.0/import success alone
does not prove cohort alignment. All legacy checks remain unchanged.

Run39666813360 passed all901 package tests but failed inside this child. Build
evidence showed same-version inherited dependencies were retained; the exact
child stage was unknown because imports precede provenance. The child now emits
only fixed ordered markers for imports, provenance, plan, prepare, decode and
reuse. The parent accepts an exact marker prefix on failure and reports its last
stage, or unknown for malformed output. No arbitrary child stdout, stderr,
traceback or payload is printed. Success still requires zero exit and the exact
success line, now preceded by all six markers. Three focused projection tests
cover every stage, malformed/private output and incomplete or failed success.

#302 adds a seventh closed stage, complete-plan, before the original success
condition. Using only image-owned bootstrap/frontend/product modules and the
same isolated public commissioning artifacts, it builds real source contracts
and compiles the complete four-node/two-binding/four-import profile. It verifies
both artifact descriptors survive exactly. A second fixed public success line
is printed only after the child passes every assertion. The synthetic website
image is never pulled or served. All original commissioning and legacy launcher
checks remain; this source packaging evidence cannot qualify production images.
# Managed PostgreSQL driver planning witness (#327)

The existing image-owned commissioning subprocess now verifies that PostgreSQL
authoring code is included in the actual driver and composes its managed contract
using an explicit fixture receiver and the existing public verifier families.
The old two-role commissioning output and exact reuse remain unchanged. Assertions
cover the projected public artifact, password file and absence of a published
PostgreSQL port. This is driver packaging/planning evidence, not managed-image
startup or published-digest qualification. The existing native acquisition and
separate PostgreSQL product readiness/storage witnesses retain their meaning.

#346 adds a storage lifecycle regression to the existing Docker check stage.
Two socket-free numeric helpers use the actual driver's checkpoint writer and
the production progress mount/directory preparation. One exits successfully with
completed progress; the other exits with a known nonzero status after a partial
schema acknowledgement. The controller reads and validates both archives after
the containers stop, then reads each again before explicit fixture cleanup.
Private intent, IDs and observations precede effects in fixture receipts; cleanup
checks exact labels/IDs and verifies absence. Unexpected outcomes retain resources
and pending evidence. No database, initialization replay, alternative runner or
full dynamic-bootstrap acceptance is implied by that component alone. It passed
the accepted #346 gate and the final #347 combined run40818456065.

Run 40702354559 stopped at test integrity before package tests: two removal
probes used bare `except NotFound: pass`, prohibited as swallowed exceptions.
The fixture now records and asserts explicit absence booleans, matching the
existing cleanup witness. Unexpected exceptions still propagate and retain
pending evidence. Production and the integrity policy are unchanged. This
correction subsequently passed the normal owning gate; the failed attempt's
unreached stages remain unreached in its own record.
## #347 dynamic authoring checkpoint

The existing prepare owner now admits the optional tuple using
`scripts.root_artifact_inputs`, refuses an image without an independently
reviewed account baseline before commissioning, and authors the three-node
dynamic fixture with actual commissioning and CPK/Secrets runtime-contract
factories. It binds explicit ordinary/management grant intent and private policy
to the public setup commitment, actual driver ID and final plan digest. Private
material uses the existing v2 index and protected files; the static path retains
its original fixture.

The selector now retains the historical account baseline and adds one exact
current CPK row from independently accepted #347 run40789512741. Its original
registry config digest is d300c4fb, distinct from the normalized OCI config51a42b83.
UID10001, primary GID10001, supplementary[100] and the passwd/group hashes come
from the actual final-filesystem evidence, not the historical row or a running
process. See [independent acceptance](https://github.com/OpenJ92/control-plane-kit-servers/issues/347#issuecomment-6483769887).
Every other image reference still refuses before commissioning. This test-only
row enables later qualification; it does not qualify the image pair, adopt a
live baseline or release any effects. The current-pair gate subsequently passed
at8bb96f9 in run40818456065 with
[independent combined review](https://github.com/OpenJ92/control-plane-kit-servers/issues/347#issuecomment-6488312730).

The next integrated candidate uses the existing commitment owner and adds actual
prepare-writer admission evidence. Its root check includes installer-file mounts,
exact tuple/source/execution and actual PID1 identity, real helper absence and
private policy readability/write denial. Authenticated HTTP revokes the fixture's
ordinary permission and management assignment; only its exact owned CPK container
is restarted. The post-restart reads require preserved revoked revisions and
registration binding, deny ordinary access and recheck private mount custody.
The normal bootstrap initialization inspection then verifies the retained binding
and timestamp. Existing pending/no-redispatch and exact resource cleanup remain.
After successful resource cleanup, only the owned material/commissioning trees
are removed; failures retain private diagnostic evidence. These new paths are
now covered by that independently reviewed actual qualified-pair gate. Its
revoked-state persistence, matching initialization binding, exact-owned resource
and private-file cleanup markers are recorded in the
[terminal evidence](https://github.com/OpenJ92/control-plane-kit-servers/issues/347#issuecomment-6488288007).

Corrected gate40815444816 passed material admission and the public revocation
probe, restarted the exact CPK container and verified Running/new StartedAt, then
failed on positional equality of Docker's mount lists. The before/after mount
records were not emitted, so an order-only difference is not proven for that run.
The fixture now sorts both lists by destination before comparing complete
records: every field, record count and duplicate remains part of equality. This
changes no production code or mount-ownership rule. Moby's reference implementation
[constructs inspection mounts by iterating its mount map](https://github.com/moby/moby/blob/v28.0.0/container/container_unix.go#L405-L420),
supporting order-independent comparison; that reference is not an attestation of
the failed runner's exact daemon version. The existing real restart witness must
still pass the unchanged post-restart permission, policy and revision checks,
initialization inspection, no-redispatch and cleanup. The corrected full witness
passed in run40818456065; this does not establish the old run's actual mount
difference or cleanup retrospectively.
See [terminal evidence](https://github.com/OpenJ92/control-plane-kit-servers/issues/347#issuecomment-6487952402).
