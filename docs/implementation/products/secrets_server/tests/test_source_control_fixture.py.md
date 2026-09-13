Source: [test_source_control_fixture.py](../../../../../products/secrets_server/tests/test_source_control_fixture.py).
Maintain with adapter file/diagnostic behavior, not receiver internals.

Tests generate two real product/Secrets-codec phase file sets and protect exact
filenames/modes, stable target/runtime/declaration, distinct public keys and no
signing-key files. CLI log cases cover clean input, old markers/exact private
values, source tokens, overflow, failed or missing retrieval status and missing
capture, asserting fixed output. Partial exclusive-create failure retains only
enumerated files without leaking or overwriting existing private input.

No HTTP verifier/provider is simulated. These tests run only in the owning Docker
suite; real reads/startup/restart belong to the maintained source smoke, with
historical mode exercised separately. No additional target-red is required by
the recorded calibrated test-flow decision for this adapter restoration.
