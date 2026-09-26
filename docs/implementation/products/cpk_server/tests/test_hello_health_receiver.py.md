Source: [test_hello_health_receiver.py](../../../../../products/cpk_server/tests/test_hello_health_receiver.py).

Issue233 uses Hello's real codec and complete source runtime contract, canonical
never-executed documents and ephemeral local keys. The registry-input guard
establishes a missing binding before source implementation; later assertions
exercise exact binding/slot, selected health keys versus defaults/static keys,
unchanged configured identity, bounded detached errors, unexpected error identity
and pure public projection. Existing product bindings coexist.

No codec or Operations state machine is copied. Identity mismatch remains
visible for Operations coverage to decide. These tests qualify only the decoder
join; they do not establish supported images, standalone packaged imports,
plan readiness, registry activation or managed deployment. Complete Hello
verification checks remain intact.
