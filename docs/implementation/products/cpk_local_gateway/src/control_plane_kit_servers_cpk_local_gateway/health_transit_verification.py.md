Source: [health_transit_verification.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/health_transit_verification.py).
Maintain this companion alongside its source.

`gateway_health_transit_verifier_from_artifact` calls the sole product-owned
configuration decoder against the exact artifact. The real verifier holds an
immutable configuration/key snapshot and parses no caller-supplied expected
authority from the token. Cryptography verifies Ed25519 over original ASCII
`header.payload` bytes; no payload reserialization substitutes for the signed
message. Headerkid selects a configured key and must equal the inner grant ID.

The closed receiver envelope for Interpreters149/Servers180 is:

```text
header: alg=EdDSA, typ=CPK-GATEWAY-NODE-HEALTH-READ-TRANSIT+JWT, kid
payload: iss, aud, iat, nbf, exp, jti, gateway_node_health_read_transit
inner: existing Core DelegatedGatewayNodeHealthReadTransitGrant descriptor
```

Compact input is exact ASCII bytes with three canonical unpadded base64url
segments. Encoded segment caps are1024/8192/86; signature is exactly64 decoded
bytes. Those caps imply9304 total bytes;12288 is a redundant early coarse cap,
not an independently reachable valid-envelope boundary. JSON is closed,
duplicate-free, nonfinite-free and depth-bounded using product-local parsing.
Outer time scalars require exactint, so bool cannot satisfy equality. All outer
claims and headerkid must match the decoded Core grant exactly.

Configuration provides expected issuer/gateway and derived audience. Per-call
context independently provides attempt, target/runtime, declaration, requested
kind and one trusted integer time observation. Configured workspace/runtime
must match that context. Core's existing comparator owns request digest,
declaration/kind/purpose/identity and exact half-open interval semantics. The
returned object is the same supplied request. Core comparison is not current
Operations approval; callers must supply independently admitted context.

No hidden clock/skew, replay cache, signature producer, private key, provider
I/O, HTTP route, target lookup or dispatch exists here. Repeated pure admission
inside the original interval is allowed. This does not promise once-only
execution, restart replay protection or future freshness. Workload signature
verification remains independent. Existing gateway probe behavior is untouched.

Expected malformed-input and InvalidSignature failures yield a fixed
candidate-free error constructed in the handler and raised after exception
context ends; BaseException propagates.
Configuration construction failures use the separate configuration error.
Tests use real local synthetic signatures, valid at/over-cap envelopes,
independent expected context and actual decoded-config key substitution. Native
implementation green remains pending; no route or mounted-file evidence is
claimed by this pure consumption witness.
