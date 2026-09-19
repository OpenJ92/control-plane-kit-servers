# Gateway self-health laws (#182)

Source: `products/cpk_local_gateway/tests/test_gateway_control.py`.

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
does not strip anything. Actual compiler ordering must retain local readiness
before connector, management path and workload progress.

Ordinary pinned Docker PR CI supplies missing-interface red and later owner green;
source is not implemented at this target stage. Public minimal status is not a
protected correlated observation or proof of authority. These package witnesses
do not establish live DNS/TLS, image qualification or downstream execution.
