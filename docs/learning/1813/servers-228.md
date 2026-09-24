# Bounded cloudflared connection evidence

Servers [#228](https://github.com/OpenJ92/control-plane-kit-servers/issues/228)
is a child of native-wrapper #188, on roadmap/1813-runtime-control from
8580249c4b397622ca80070f610577986dce5c40. The accepted plan is #188 comment
5816509194; Meridian's plan PASS5816537364 fixed header/count/schema limits,
consumer current-authority/expiry checks and honest shared-UID token wording.

The native 2026.6.1 readiness handler supplies actual connection count, unlike
its unconditional /healthcheck. Native 200/positive and503/zero are determinate;
inconsistent/malformed/absent observations remain unknown. The product owns
meaning and a fixed loopback reader; Docker only schedules bounded samples.
The original private/public management observation branches remain independent.

Pinned upstream Dockerfile places cloudflared at /usr/local/bin/cloudflared and
uses65532:65532. main.go installs tunnel.Flags as global flags, supporting the
fixed --metrics argument while retaining CMD tunnel run. Source verification
does not substitute for packaged-image/UID/command witnesses.

The intended contract is one zero-argument read, 2-second total monotonic budget,
8KiB aggregate status/headers,1KiB body, uint64 count and strict exact JSON fields,
256-byte versioned output. No proxy, DNS, redirects, retries, credential input,
raw diagnostics or public listener. Same-container UID access is not credential
isolation; reader implementation deliberately does not read token material.

Target checkpoint6e4661f7e7eb5dc5b929b5898ae63052881a000f contains10 new law methods,
the6 unchanged product declarations and an explicit unimplemented interface.
Owning CI36017103830/job107692339549 passed26 policy and48 root methods, then
collected16 connector methods with37 expected subtest errors from NotImplementedError.
No collection/import/fixture/daemon failure caused this red. Log SHA256:
291d4c138865b238f13feff3494d45409405db667f80cd95d32edcd1f836b240.
Application implementation and packaged witness are pending at this checkpoint.

The later #148 consumer must inspect only an authorized exact target and latest
sample; verify effective pinned image/configuration, ownership, incarnation,
sample freshness and original stage authority before I/O and acceptance. A
healthy aggregate cannot hide a failed latest sample; recent evidence cannot
extend original expiry. Those are handoff obligations, not implemented here.

Parent #188 still owes persistent SDK control and bidirectional native/wrapper
failure, signal, exit and shutdown behavior. This reader is not a replacement
for that deliverable. Historical published descriptors remain unchanged. No live
image, provider, token, DNS or tunnel effect was performed by this source work.
