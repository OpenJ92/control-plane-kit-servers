Source: [test_control_receiver.py](../../../../../products/cpk_server/tests/test_control_receiver.py).
Maintain with CPK receiving, startup and authority contracts.

Focused laws cover real artifact/config round trips, all three complete
historical contract comparisons, closed/typed malformed input and fixed errors,
opened-file bounds/symlink/directory/FIFO/missing cases, required configuration and
actual SDK collision before any Operations factory call, actual SDK installation
before schema plus schema-failure propagation, signed local liveness and separate
instance authorities, and missing config before a listener/pure configuration
imports. The tests reuse owner RecordingService/DeterministicVerifier fixtures.
Existing199 host tests retain all routing/status/field/order assertions and now
receive required control at actual create_app; the SDK-only reference stays real.

No schema effect is moved into health. Zero-work counters concern post-startup
requests; startup schema work is asserted separately. No dependency health or
cross-restart replay/durable workflow guarantee is invented.

#237 keeps every existing test method and translates to Core common receiver
configuration, purpose-indexed verifier families, receiver request/result codecs,
CPK_WRAPPER_CONFIGURATION_FILE and the actual SDK install_cpk_wrapper. Complete
source contracts retain their existing fields and add the common file binding.
Malformed raw documents reach the product receiving decoder; invalid construction
of Core's own value is checked at Core's existing exception boundary. A new real
host law holds installed target/keys fixed across two caller contexts and refuses
each foreign workspace/runtime/node/socket/receiver-ID, without operator work.
No permanent graph revision is installed and no authority is inferred from token
self-description. Kepler target authorship; independent review and full gate pending.
