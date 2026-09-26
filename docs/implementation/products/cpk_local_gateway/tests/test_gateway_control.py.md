Source: [test_gateway_control.py](../../../../../products/cpk_local_gateway/tests/test_gateway_control.py).
Maintain this companion alongside its source and selected dependency contracts.

# Gateway self-health laws (#182)

Target stage follows reviewed plan5743544407 and source-contract correction
5743553420 on Servers182. Seven focused tests exercise actual SDK surface/health
installation, authorization before callbacks, local serving lifecycle including
exceptional shutdown, downstream-failure independence, complete real contract
compilation/ordering, strict public configuration and actual selected-file startup.
Exceptional shutdown enters `app.router.lifespan_context(app)` directly and
raises a sentinel through its async exit before checking UNHEALTHY. Normal
TestClient HTTP checks remain separate; an exception in their body alone would
not prove the application lifespan's exceptional-exit path.

New laws join SDK/gateway/Core owners rather than duplicate them. Existing #180
relay, source-slot, startup-selection/fixed-port and historical-image tests remain
governing and unchanged during target red. Their required third-file/signature
adaptation belongs with source implementation after causal red and target review.
The complete managed source contract must replace its own two legacy independent
HttpChecks with the actual SDK surface, with no health_path; the graph fixture
does not strip anything. Under the adopted Core f1e fresh-bootstrap law,
gateway start precedes allocation and connector creation; PATH and CONNECTED
are independent observations after creation. GATEWAY_INGRESS_READY resolves
the real gateway-own control surface after PATH. Workload progress requires
both gateway readiness and CONNECTED. Fresh bootstrap contains no private
GATEWAY_LOCAL_READY stage; retained-runtime behavior belongs to Core's tests.

Ordinary pinned Docker PR CI supplies missing-interface red and later owner green;
the reviewed target stage precedes implementation. Public minimal status is not a
protected correlated observation or proof of authority. These package witnesses
do not establish live DNS/TLS, image qualification or downstream execution.

Original target `a9a96dc` ran ordinary CI35455965847/job105931156091:26 support,
48 root and6 prior product tests passed; gateway56 had49 existing green and
exactly7 missing-interface failures,0 errors. Integrity inventoried443 tests;
later products/runtime witnesses did not execute after the intended stop.
Corrected target `3eb6082` separately fixes exceptional-lifespan causality and
its companion, reviewed before source. Its deeper assertion first executes in
implementation CI; no duplicate red was run behind the unchanged missing guard.

Source plus coordinate-expectation correction `40a3531` passed ordinary pinned
CI35456792284/job105933403088 (composition `0092290`): 26 support and all 443
package tests, including gateway 56/all 7 new laws. The corrected exceptional
lifespan assertion executed green. Existing source/published baseline and numeric
runtime witnesses completed with exact owned cleanup and final residue audit.
[PR218 evidence](https://github.com/OpenJ92/control-plane-kit-servers/pull/218#issuecomment-5743768008)
records the exact head, log digest, review and source/image/live limits.
