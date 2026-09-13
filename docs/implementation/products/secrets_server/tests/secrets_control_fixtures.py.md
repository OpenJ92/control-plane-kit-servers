Source: [secrets_control_fixtures.py](../../../../../products/secrets_server/tests/secrets_control_fixtures.py).
Maintain with the source file and accepted service/Core/SDK contracts.

This product-test helper creates actual typed public configuration using the accepted Secrets constructor/declaration, Core target/runtime values and separate SDK public verifier families. Ephemeral Ed25519 private keys are generated only to obtain public keys and are discarded; no grant, secret file, provider, socket or custody state is created. Secrets is imported inside the helper after the test's explicit product-interface guard. Current missing-interface red must not be mislabeled as having exercised this downstream fixture.
