Source: [products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py](../../../../../products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite checks the gateway's product value, process boundary and cryptographic
verification using Core codecs, fresh synthetic Ed25519 keys, fixed clocks,
FastAPI TestClient and patched target I/O. It does not demonstrate live target
connectivity or the deployed OCI image.

Descriptor cases cover canonical roundtrip/content digest, catalogue agreement,
sockets/port/environment/lifecycle shape and instantiation without importing the
process. Compiled disconnected, HTTP-only and Postgres-connected topologies
show conditional password-reference delivery. The test named removal/revocation
compares desired graph shapes; it does not revoke a running process credential.

The denial matrix spans missing/malformed/forged grants, issuer/key/audience/
workspace/gateway/request/time mismatches for both probe kinds and asserts no
target dispatch. Separate cases test exact request acceptance, a valid grant
for an undeclared target and public minimal health. These are selected negative
cases, not a complete JWT parser or exception-redaction audit.

Eight concurrent uses of one unexpired grant produce one acceptance and seven
replays in one cache. A fresh verifier/cache accepts it again: restart retention
is explicitly absent. The case does not cover nominal expiry versus configured
skew or header-kid/grant-key disagreement.

Direct HTTP dispatch patches the _http_status helper and checks the configured
target path; the Postgres descriptor example omits password configuration.
Those observations do not exercise real HTTP error handling, DNS boundaries or
database credentials. Source/Docker/smoke checks assert selected text rather
than executing the scripts. In particular, the private-probe smoke text test
does not repair its missing signed-auth startup/request material. The structural
grant helper is imported and run by its own case, proving synthetic protocol
roundtrip with historical-shaped identifiers, not historical/live authority.

Related source and evidence: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py](../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py), [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py](../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py), [products/cpk_local_gateway/product.cpk.json](../../../../../products/cpk_local_gateway/product.cpk.json), [scripts/cpk_local_gateway_private_probe_smoke.sh](../../../../../scripts/cpk_local_gateway_private_probe_smoke.sh), [scripts/cpk_local_gateway_structural_grant_check.py](../../../../../scripts/cpk_local_gateway_structural_grant_check.py).
