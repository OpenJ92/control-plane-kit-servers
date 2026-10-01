# Gateway self-health fixtures

Source: `products/cpk_local_gateway/tests/gateway_control_fixtures.py`.

Synthetic product-local public trust and actual #180 relay configuration feed
the real SDK composition. Credentials use Core grants and synthetic Ed25519
keys; no copied verifier or durable authority service is present. Downstream
transport deliberately returns503 and records calls. The topology builder copies
the complete returned source contract, including verification and configuration
artifacts, into actual Core graph values without stripping obligations. No
fixture creates containers, performs provider effects or establishes live TLS.

#237 receiving target translation precedes gateway production. All existing
method identities, original signature/time/denial/body/closure/callback assertions
remain. Own health uses actual Core ReceiverNodeControlConfiguration and receiver
V2 request/grant/result values. The independently frozen obsolete own-config
admission specimen is unchanged. Transit/relay artifacts bind the full gateway
receiver target; each workload binding carries full target/declaration/origin.
Separate duplicate runtime fields are removed, and canonical receiver V2 transit
advertisement/envelope/configuration profiles replace the old family.

Negative laws cover full workspace/runtime/node/socket/receiver scope and both
request authority fields without deriving expectations from signed input.
Otherwise-valid foreign-runtime/workspace pairs use matching foreign gateway
scope so construction cannot stand in for actual receiver refusal. Transit
verification accepts repeated original requests under either synthetic authority
context for the same installed identity; that is protocol congruence, not current
Operations permission. Mixed and obsolete profiles refuse at actual boundaries.

The workload fixture installs the actual common FastAPI SDK wrapper. Its ASGI
transport enters/exits that exact app's real lifespan around dispatch so readiness
can reach the protected callback; direct TestClient prerequisites own their own
lifespan. Gateway same-app own readiness and exceptional shutdown assertions are
retained. Startup witnesses redirect public file placement only, supply the
single CPK_WRAPPER_CONFIGURATION_FILE binding and mode0444, then invoke actual
main/loader/decoders/application. Full source contract/graph/selected-slot and
historical image assertions remain; no private lifecycle or verifier substitute.

This is target-only static preparation, not executable green. Initial929f829 red
proves missing obsolete own-profile refusal only. New receiving closure and the
unchanged whole Servers/paired Interpreter gates remain required. No host test,
manual runner, provider, credential publication or live deployment occurred.
