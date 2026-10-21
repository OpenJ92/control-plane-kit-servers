Source: [test_root_commissioning.py](../../../../../products/cpk_server/tests/test_root_commissioning.py).

#301 target-only checkpoint. The missing public module is asserted inside each
test, preserving collection and making baseline failure causal. No application
implementation is included. The owning unchanged Docker gate is the only
execution context; these keys are isolated test fixtures, never production input.

The tests extend existing bootstrap laws for deterministic plans, refusal before
effects and preservation of uncertain state. New laws cover durable intent before
ID allocation, durable receiver IDs before key generation, exactly two Ed25519
purposes, actual Core/CPK/Secrets configuration decoding, private custody modes,
nonblocking contention, completed immutable reuse and public-only results.
Persistence failure injection observes actual file descriptors at os.fsync;
it does not replace the lifecycle or model a separate implementation.

Complete state is not authorization to repair it. Missing/corrupt/mismatched
keys, modes, manifests or unknown entries must hold without reminting. Error
payloads cannot retain private exception context. Files have explicit bounds;
private bytes and private-file digests are excluded from public metadata.

The corresponding real-driver witness runs in the established bootstrap stage,
using only image-owned product source paths plus installed dependencies. Unit
green alone cannot establish that packaging boundary. Existing launcher setup,
no-redispatch and cleanup assertions remain in force. Production commissioning,
image publication and later website wiring remain outside this target set.
