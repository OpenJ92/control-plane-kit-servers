Source: [cpk_http_host_fixtures.py](../../../../../products/cpk_server/tests/cpk_http_host_fixtures.py).

Servers #237 targets use the actual Core ReceiverNodeControlConfiguration,
full logical receiver target and purpose-indexed verifier families. The receiver
ID is deterministic synthetic fixture data; private Ed25519 keys remain ephemeral.
Caller NodeControlAuthorityContext is separate from installed configuration.
`token` signs actual receiver health/surface grants for the original request.
`verifier_family` and `with_health` only arrange fixture public trust; they do not
implement admission, current authority or a replacement trust DTO.

The SDK-only reference host uses real install_cpk_wrapper. The production CPK
host remains responsible for its own installation. Explicit issued-at/lifetime
inputs preserve the existing source-smoke fixture contract; default test time is
100/100 seconds. No test was executed for this Kepler-authored target tranche.
