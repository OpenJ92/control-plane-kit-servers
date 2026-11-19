# Frontend composition tests (#243)

Eight new-law test methods exercise the public pure authoring interface. Fixture
OCI digests are explicitly synthetic values; tests never build, pull or publish
them. Product tests preserve the supplied image and port/upstream agreement,
material-derived identity, canonical descriptor and explicit unverified state.
Negative cases refuse bad origins/ports, unpinned input, incorrect ingress target
or node alias, and inconsistent or incompatible connector descriptors.

Graph tests compile/validate/roundtrip deterministic values and inspect only the
frontend node/runtime/ingress set with no authority deliveries. Graph names are
not workspace authority; no test claims actual cross-workspace provider isolation
or live readiness. Existing `./test.sh` owns executable validation. Red evidence
is PR244's immutable tests-only b704677 checkpoint; two graph-name field references
were corrected against the actual Core type before green implementation.
