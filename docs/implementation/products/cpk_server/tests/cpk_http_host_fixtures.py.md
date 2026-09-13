Source: [cpk_http_host_fixtures.py](../../../../../products/cpk_server/tests/cpk_http_host_fixtures.py).
Maintain alongside installed SDK host tests.

Local synthetic CPK http-api target/runtime and V2 liveness declaration compose
actual Core values with separate purpose-typed SDK public verifier keysets.
Private test keys stay in memory; fixed test clock and bounded grants allow
comparison of real SDK-only/composed hosts. No product configuration default,
network listener, provider credential, key file or durable issuer is introduced.

Servers200 now returns the actual CpkControlConfiguration. Issue199's signed
fixture accepts explicit issued-at/lifetime values for the owned source smoke;
default unit-test time remains100/100 seconds. The production CPK app installs
SDK itself; the helper installation function is the SDK-only reference host.
