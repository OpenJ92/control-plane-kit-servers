# Managed cloudflared executable target draft

Source: [packaged_managed_witness.py](../../../../../products/cloudflared_connector/tests/packaged_managed_witness.py).

Servers #284 owns this target draft, invoked through the single new product stage
of the existing Docker `test.sh`. It has not run or passed exact target review.
The managed Dockerfile and notice manifest remain unimplemented. Missing build
material is not causal-red evidence; do not run this draft as an apparatus probe.

The real-image lane checks image launch/health metadata, actual installed native
version and SDK/Core source coordinates, dependency license metadata and exact
notice blobs. It uses real 0444 SDK configuration and same-UID 0400 synthetic
native token delivery. Its test-only HTTP client receives current-time generated
credentials by a separate readonly fixture file, never argv or logs. The normal
entrypoint remains unchanged, without native launch overrides or static edges.

The helper observes numeric Python PID1, one real native child/session and fixed
native environment, then authorized static/liveness/readiness and denied reads.
It bounds startup and permits only connection-refused polling on that same native
identity; an early native exit cannot become success. Real-native stop uses the
selected unmodified interpreter. It must return cleanly while the native identity
was alive immediately before the call. These endpoint reads do not prove
before-protected-I/O ordering beyond existing SDK/product tests.

The separate controlled TERM-ignoring PID1 has handler-ready/TERM receipts and one
selected stop. Its bounded Engine event query requires exact identity,
integer timeNano, unambiguous15/9/die137 and fixed inclusive9–11second
corroboration. Cleanup/competing events cannot supply its proof. This is a chosen
empirical interval, not timing accuracy or a useful-execution lower bound.
A separate controlled fatal-PID1 case observes an owned child session before
SIGKILL and Docker's exited namespace/Pid0 afterward; it does not scan all host
processes or claim graceful drain. Exact-owned cleanup must complete before PASS.

**Concrete open target gap:** actual effective timeout must resolve independently.
Docker's Info schema does not expose a daemon default timeout. This draft
accepts only an explicit inspected container timeout10 and otherwise yields
`stop_profile_unproved`; it does not silently add a timeout override. The normal
creation path supplies none. Before target acceptance, reviewers must establish
the actual-version/default evidence path or retain an explicit blocked profile.
Generic Linux documentation is insufficient, and an invented API field is not a
resolver. This is reported for review before image implementation or a new run.

The script is compile/discovery-safe, but the unit suite does not award image
coverage merely by compiling it. No alternate harness, tests of Docker internals,
retries, fake-native substitution or production fault switches are introduced.
