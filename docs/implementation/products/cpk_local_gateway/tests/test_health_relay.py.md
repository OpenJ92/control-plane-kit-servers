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

Status: target tests only, not executed yet. Missing-module assertions occur after
valid fixture construction. Guarded assertions are not credited until source runs
them green. Owning validation is unchanged Docker ./test.sh via normal PR CI.
