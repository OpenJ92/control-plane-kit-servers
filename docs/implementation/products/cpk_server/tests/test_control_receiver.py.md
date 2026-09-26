Source: [test_control_receiver.py](../../../../../products/cpk_server/tests/test_control_receiver.py).
Maintain with CPK receiving, startup and authority contracts.

Seven focused laws cover real artifact/config round trips, all three complete
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
