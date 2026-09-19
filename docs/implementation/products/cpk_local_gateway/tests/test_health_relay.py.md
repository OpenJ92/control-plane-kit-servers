# Closed gateway health relay laws

Governing design: Servers #180 comment5733806716 and startup/port amendments
5733823699/5733837190. Tests preserve the original Core request and semantic result
through real selected transit and SDK verifiers. Structural pair mismatch and
transit/context refusal have zero outbound requests; a matching bad workload
signature reaches the SDK but never its protected callback.

Both kinds, all four semantic outcomes, repeated original-window reads, exact
management port, request/result framing, response cancellation, stream byte caps,
proxy/redirect/header exclusion and context-free failures are covered. HTTPX
transports are injected at its I/O boundary, not substituted for authentication.
These are package connection laws, not deployed-network or published-image proof.

Original target c0f1f94 produced reviewed missing-interface red after valid fixture
construction. Subsequent fixture and source-policy corrections are historical;
all guarded bodies executed green at ba9bc249 in normal CI35379205171. The unchanged
owning Docker gate passed26 support and436 package tests, including all15 new laws.
[Exact evidence and limits](https://github.com/OpenJ92/control-plane-kit-servers/pull/216#issuecomment-5734352881).
