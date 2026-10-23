Source: [test_protected_input_composition.py](../../../../../products/cpk_server/tests/test_protected_input_composition.py).

#317 specifies the missing optional custody port and accepted provision owner
composition. The actual provider composition must forward the same custodian
without credential IO. The real factory matrix requires both independent
authority and custody, preserves shared UoW/clock, and distinguishes unavailable
501 from the enabled owner's malformed-body400 before durable/provider work.
A stricter independently configured policy denies before payload decoding and
custody; it does not model production hot reload. Existing generation-only
matrix and #316 transport tests remain unchanged.

These are unexecuted target tests awaiting concrete fixture/causality review.
Missing-port/owner assertions are interface-red only until the actual normal
Docker-backed gate executes. The later authenticated preparation witness owns
successful encrypted custody and real PostgreSQL composition evidence; this
matrix does not claim those effects happened.
