Source: [test_protected_input_composition.py](../../../../../products/cpk_server/tests/test_protected_input_composition.py).

#317 specifies the missing optional custody port and accepted provision owner
composition. The actual provider composition must forward the same custodian
without credential IO. The real factory matrix requires both independent
authority and custody, preserves shared UoW/clock, and distinguishes unavailable
501 from the enabled owner's malformed-body400 before durable/provider work.
A stricter independently configured policy denies before payload decoding and
custody; it does not model production hot reload. Existing generation-only
matrix and #316 transport tests remain unchanged.

Normal CI40029935612 ran615 CPK methods with exactly three intended failures:
forwarding returned None at line29, and the two other methods failed their first
missing-port assertions at lines39/74. No later matrix, owner-construction or
current-policy assertion in these methods was reached. Existing612 methods passed.
The three target methods are unchanged for the implementation's green attempt.
The later authenticated preparation witness owns successful encrypted custody
and real PostgreSQL composition evidence; it was not reached in this red run.
