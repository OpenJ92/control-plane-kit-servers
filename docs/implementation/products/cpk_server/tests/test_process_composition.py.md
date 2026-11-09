Source: products/cpk_server/tests/test_process_composition.py.

This process-level boundary keeps executor, observer and ingress ports distinct
and verifies product/import ownership. Its static composition fixture explicitly
sets both optional verification supports to None, as the real bootstrap config
defaults do. An unbounded Mock otherwise fabricates two different support objects
and correctly trips the real shared-identity invariant. The existing port/fold
assertions and production fail-closed rule are preserved. Enabled support sharing
remains covered by the managed startup/native registration source controls.
