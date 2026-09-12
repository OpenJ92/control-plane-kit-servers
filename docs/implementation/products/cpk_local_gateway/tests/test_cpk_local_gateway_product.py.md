Source: [products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py](../../../../../products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite checks the gateway's product value, process boundary and cryptographic
verification using Core codecs, fresh synthetic Ed25519 keys, deterministic
clocks, FastAPI TestClient and patched target I/O. It does not demonstrate live
target connectivity or the deployed OCI image.

Descriptor cases cover canonical roundtrip/content digest, catalogue agreement,
sockets/port/environment/lifecycle shape and instantiation without importing the
process. Compiled disconnected, HTTP-only and Postgres-connected topologies
show conditional password-reference delivery. The removal/revocation test
compares desired graph shapes; it does not revoke a running process credential.

The denial matrix spans missing/malformed/forged grants, issuer/key/audience/
workspace/gateway/request/time mismatches for both probe kinds and asserts no
target dispatch. Separate cases check exact request acceptance, valid grants
for undeclared targets and public minimal health. These are selected negative
cases, not a complete JWT parser or exception-redaction audit.

Eight concurrent uses of one unexpired grant produce one acceptance and seven
replays. A fresh verifier/cache accepts it again: restart retention is absent.
The full-window regression uses skew 0/5/30 and actual signed consumed/fresh
grants to distinguish nominal expiry, grace and the exclusive E+S boundary;
it also preserves the early-issued inequality. Capacity one cannot evict an
unexpired protection, and can be reclaimed at its acceptance deadline.

Rollback cases observe denial and equal-time recovery after either an accepted
forward grant or a temporally denied forward grant; attempted requests at lower
times neither erase prior protection nor consume a new JTI. The request/time
precedence case proves mismatched requests do not sample the cache clock or
consume the grant; successful admission samples once. These are public outcomes,
not assertions about private map/high-water layout. Source review additionally
checks that the sample and decision occur under one lock.

Servers #176 causal red used the prior public constructor wiring. Green moves
only clock/skew inputs to the cache owner; behavioral assertions are unchanged.
No new provider matrix, sleep-based test or compatibility helper is introduced.

Direct HTTP dispatch patches _http_status and checks the configured target path;
the Postgres descriptor example omits password configuration. Neither executes
real target I/O. Source/Docker/smoke checks assert selected text. The private-probe
smoke text test does not repair missing signed-auth startup/request material.
The structural grant helper is imported and run, proving a synthetic protocol
roundtrip with historical-shaped identifiers, not historical/live authority.

Related source and evidence: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py](../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py), [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py](../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py), [scripts/cpk_local_gateway_structural_grant_check.py](../../../../../scripts/cpk_local_gateway_structural_grant_check.py).
