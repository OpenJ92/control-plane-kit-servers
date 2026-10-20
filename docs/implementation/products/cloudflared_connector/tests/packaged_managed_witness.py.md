# Managed cloudflared executable target draft

Source: [packaged_managed_witness.py](../../../../../products/cloudflared_connector/tests/packaged_managed_witness.py).

Servers #284 owns these targets, invoked through the single new product stage
of the existing Docker `test.sh`. Exact targets at f30abdf earned Meridian TARGET
PASS. Owning PR gate39381573535 on tested merge30c4de9 (tree equal to source
5609d35) passed all747 package methods and built the managed image with103
verified notices, then failed the detached helper exit check. The snapshot was
combined-container exited/1/Pid0; helper mode and reason were discarded. This
does not diagnose native, SDK, configuration or DNS cause. Runtime qualification,
whole-stage cleanup and final residue acceptance remain uncredited.

The real-image lane checks image launch/health metadata, actual installed native
version and SDK/Core source coordinates, dependency license metadata and exact
notice blobs. It uses real 0444 SDK configuration and same-UID 0400 synthetic
native token delivery. Its test-only HTTP client receives current-time generated
credentials by a separate readonly fixture file, never argv or logs. The normal
entrypoint remains unchanged, without native launch overrides or static edges.

The helper observes numeric Python PID1, one real native child/session and fixed
native environment, then authorized static/liveness/readiness and denied reads.
Before the first native observation it allows bounded pre-spawn scheduling while
the container remains running. After observing native, only connection-refused
management polling on that same identity is permitted. No replacement launch.
The public result codecs validate complete schema/request digest, target context,
declaration and kind; capabilities must equal the exact expected declaration.
Real-native stop uses the selected unmodified interpreter. Profile reads happen
before the final native snapshot. The latter observes alive immediately before
the call, not an atomic guarantee against exit racing signal delivery.

Helper execution uses detached Docker exec, not the unbounded upgraded socket
reader. Completion polling checks the deadline with finite one-second API
requests. Result retrieval uses no Docker archive or streamed socket: helpers
write one exclusive file capped4096bytes in a dedicated run-owned results
directory, mounted writable only as test instrumentation. After completion the
controller opens its local file with NOFOLLOW/NONBLOCK, requires regular mode0400
and numeric owner65532, reads at most4097bytes and checks stable metadata/size
before parsing and unlinking. Deadline/refusal enters exact-owned cleanup,
terminating remaining helpers with their container. Remaining named result
files are removed only after container cleanup. This fixture channel contains
observation metadata, never credentials; it is shared custody, not isolation.
Neither scheduler latency nor an in-flight finite request/local filesystem
operation is claimed to have a zero-overrun wall-clock guarantee.
These endpoint reads do not prove before-protected-I/O ordering beyond existing
SDK/product tests.

The reviewed diagnostic correction retains successful payloads unchanged.
Only the four observation modes can write a failure record, exactly
`{"outcome":"failure","reason":<allowlisted code or "helper_exception">}`.
Nonzero exec completion retains controller-owned mode and actual exit code,
then attempts the same bounded file read within the remaining deadline. It emits
a closed availability state (`valid_error`, `unavailable`, `invalid`, or
`deadline_exhausted`) and always preserves `real_native_observation_failed`.
Missing or invalid diagnostics cannot replace the original failure or earn
success. A reserved failure record with exit zero is also refused.
No exception messages/classes, native output, configuration, response bytes or
credentials enter diagnostics. A helper reason identifies an observed check,
not necessarily the cause of combined-process exit. Failed diagnostic writes
are best effort; existing exact-owned cleanup handles remaining files.

Five focused diagnostic tests exercise these laws at the completion boundary.
They do not simulate Docker or award runtime acceptance. This correction awaits
local source review before any push; executable validation has not been rerun.

The separate controlled TERM-ignoring PID1 has handler-ready/TERM receipts and one
selected stop. Its bounded Engine event query requires exact identity,
integer timeNano, unambiguous15/9/die137 and fixed inclusive9–11second
corroboration. The legitimate initial start before TERM is allowed; starts within
the TERM-to-terminal interval and restarts are refused. Cleanup/competing events
cannot supply its proof. This is a chosen
empirical interval, not timing accuracy or a useful-execution lower bound.
A separate controlled fatal-PID1 case observes an owned child session before
SIGKILL and Docker's exited namespace/Pid0 afterward; it does not scan all host
processes or claim graceful drain. The inner controller PASS requires its container
cleanup. Only the shell stage's final success after image/fixture cleanup earns
whole-stage acceptance; the later global residue audit remains separate.

Actual effective timeout must resolve independently. Docker's Info schema does
not expose a daemon default timeout. Kepler identified one bounded source path:
Moby28.5.1 commit `f8215cc266744ef195a50a70d427c345da2acdbb` uses fixed Unix10
when container StopTimeout is absent. The draft matches that exact advertised
version and its full or at-least-seven-character commit prefix, or requires an
explicit inspected container timeout10. Unknown/configurable defaults remain
`stop_profile_unproved`; no timeout override is added. It records actual safe
Engine/container/SDK fields before refusal and requires the observed SDK7.2.0,
whose omitted-timeout call was read in primary source.

Source anchors at that immutable Moby commit: `container/container.go:597`
returns the explicit timeout or default; `container/container_unix.go:26` defines
Unix10; `daemon/stop.go:57` selects it unless request options override it.
This is source-identified compatibility plus required empirical corroboration,
not binary attestation or a claim that the current runner matches. No actual
runner tuple has yet been observed. Generic Linux documentation alone and
invented API fields remain insufficient.

The script is compile/discovery-safe, but the unit suite does not award image
coverage merely by compiling it. No alternate harness, tests of Docker internals,
retries, fake-native substitution or production fault switches are introduced.
