Source: [test_http_sample_configuration.py](../../../../../products/cpk_local_gateway/tests/test_http_sample_configuration.py).
Governing work: [Servers #163](https://github.com/OpenJ92/control-plane-kit-servers/issues/163).

The owning source gate at8a9838d passed75/76 gateway tests; the real-main
composition assertion returned2 instead of0. Earlier product tests remove gateway
modules from sys.modules between cases. This test held control_configuration
from collection, so its reader patch missed the current module imported by real
server.main. The current reader correctly rejected missing wrapper configuration
in the cleared test environment. This establishes a test-input lifetime issue,
not a demonstrated product startup defect.

Resolve control_configuration in setUp and use that same module for fixture
construction and the existing reader patch; require that active reader mock is
called exactly once with no arguments. Preserve real server.main, artifact
loading, actual application composition, captured uvicorn app, expected exit0
and both HTTP-sample/V2 route assertions. No product checks, fixtures, environment
requirements or outcomes are weakened. This correction is source-only and has
not executed; independent combined review and a separate owning Docker rerun
release remain required. Original failed log is retained without alteration.
