Source: [test_http_host.py](../../../../../products/cpk_server/tests/test_http_host.py).
Maintain alongside product transport compatibility.

Tests call real create_app, replacing only the effectful operations factory with
existing RecordingService/DeterministicVerifier fixtures from the neutral boundary
tests. All74 current routes must reach auth before malformed payload decode;
exact workspace creation and raw query paging must preserve boundary responses.
The compatibility table checks bodies, methods, Allow sets, strict slashes,
legacy public health and MCP parsing/auth/dispatch order, with zero-work counters.

A future literal contract prefix is routable; dynamic, empty and reserved first
segments and unsupported methods reject before route mutation. Real SDK-only and
composed apps receive the same signed/denied/canonical/unknown/encoded/slashed
requests. SDK success is asserted as well as equality, and no operator auth or
service is invoked. Root-wildcard collision rejection stays real SDK behavior;
non404/405 application errors keep FastAPI status/body/headers.

The product-owned cpk_http_host_fixtures.py generates ephemeral separate Ed25519
static/health test authority entirely in memory. It is not a production receiver,
issuer service or deployable default. Existing18 neutral boundary laws remain.
Only the normal Docker-backed ./test.sh executes these tests. No source-host or
published-image result establishes a production CPK wrapper in this child.

Parity compares the entire neutral response after standard JSON serialization,
preserving wire-list representation of tuple-valued principal grants. The first
hosted run exposed two in-memory tuple versus JSON list assertion mismatches;
this expectation correction changes no production behavior or asserted field.

Servers200 supplies the actual required CpkControlConfiguration and fixed test
clock to create_app. The product app now installs SDK itself; only the reference
app uses the fixture installer. All199 compatibility assertions remain, including
full JSON parity and zero operator work for protected routes.
