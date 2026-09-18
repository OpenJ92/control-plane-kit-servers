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

Validation: source/test head ba9bc249 passed full owning CI35379205171, including
all15 new laws and49 gateway tests. Original causal red and the reviewed fixture
and source-policy corrections remain historical evidence on PR216.
[Exact result and limits](https://github.com/OpenJ92/control-plane-kit-servers/pull/216#issuecomment-5734352881).

Source review strengthens malformed-route handling: closed kind validation
precedes ASCII path encoding, so a non-ASCII unknown kind receives bounded400,
with zero outbound requests, rather than an internal500. The existing framing
test carries this single regression case. Explicit bounded failure objects are
constructed in catch handlers and raised outside their exception context, as
required by the owning integrity policy.
