Source: [test_health_transit.py](../../../../../products/cpk_local_gateway/tests/test_health_transit.py).
Maintain this companion alongside the tests.

These targets own the gateway product's public configuration and its pure
consuming Ed25519 health-transit verifier. Synthetic keys and actual Core
request/grant values are constructed before missing-module guards, so the
target-only gate distinguishes absent207 behavior from collection/setup failure.
No guard skips tests or imports a reference implementation.

Configuration tests cover closed profiles, exact roles/purpose, actual Ed25519
key parsing, bounds, immutable deterministic key ordering, duplicate identities,
fixed artifact slots and candidate-free errors. The actual artifact factory
must consume selected bytes: replacing A trust with B under a newly computed
valid digest changes signature acceptance; A+B preserves overlap. No separately
supplied hash or declaration stands in for receiver decoding.

Signature tests use the original compact input, independent expected context,
both health kinds, exact half-open time, repeated pure verification and strict
outer/inner/key correspondence. Duplicate/missing/unknown JSON, nested candidates,
noncanonical base64url and signature/segment bounds fail closed. The12288-byte
aggregate is an early coarse cap; valid segment maxima already imply9304bytes,
so no independent aggregate-boundary acceptance is claimed. Diagnostics use
fixed messages/boolean assertions and indexed cases rather than token/key dumps.
Independent limit witnesses use valid JSON padded to16384/16385 bytes,
16/17 distinct valid keys, and freshly signed valid JSON at1024/8192 encoded
segment caps versus first reachable over-cap lengths1026/8194. Malformed
framing and duplicate cases are separate negative laws.

Existing probe/cache/HTTP tests remain unchanged. These targets prove no replay
storage, approval/current-attempt authority, HTTP relay, provider I/O, mounted
artifact delivery or image adoption. Core owns semantic comparison; Operations
and later composition/delivery issues retain their respective gates.

Status: native target-red reached all12 intended missing-configuration guards;
deep assertions remain unexecuted until source green. Both static and causal
reviews passed. Governing law/interface design and review are recorded on
Servers207 comments5689740764 and5689760259; red evidence is PR209comment5689866072.
