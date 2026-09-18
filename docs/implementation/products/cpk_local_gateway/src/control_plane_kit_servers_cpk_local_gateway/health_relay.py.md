# Closed authenticated health relay

Source: `products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/health_relay.py`.

`POST /cpk/health/{kind}` accepts the closed
`cpk-gateway-health-relay-request.v1` envelope: target_id, attempt_id, existing Core
request descriptor, and workload credential. The single Authorization bearer is
transit authority. Configured target/runtime/declaration and actual route kind
constrain that signature. Envelope attempt ID is signed correlation, not current
Operations eligibility, revocation or once-only use. Original-window repeated
reads are permitted; request ID/digest are preserved.

The gateway structurally checks the workload JWT's exact family, outer/inner
congruence, target/audience/runtime/kind/declaration/request/digest using existing
Core codecs. It deliberately does not authenticate workload signatures: a
matching forged signature may reach SDK, which rejects before protected callback.
Transit/context/structural-pair denials occur before target HTTP.

HTTPX uses no environment proxies, redirects or retry. One bodyless GET goes to
the configured origin plus `/__control/health/{kind}`, forwarding only the workload
bearer and fixed accept headers. Input and full response interpretation each have
a five-second deadline. Input streams stop at16384 bytes; response streams stop
at446 bytes; nonidentity content encoding is rejected before body consumption.
The original-context Core result codec preserves all four semantic outcomes.
Non200, malformed, stale or oversized results are nonsemantic failures.

Fixed no-store errors never contain URLs, peer bodies, credentials or exceptions.
Client/response contexts close on success, refusal or cancellation. No durable
history or retry is created here; #147/#1860/#181 own downstream interpretation
and history. Current package tests use actual SDK ASGI transport, not deployment.

Validation pending first source CI; original causal-red evidence and corrected
immutable target checkpoint are recorded on PR216.
