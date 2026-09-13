Source: [test_hello_dependencies.py](../../../../../products/hello_server/tests/test_hello_dependencies.py).

Boundary tests retain dependency semantics while exercising max/max+1 declaration,
name, URL and environment-name limits. Controlled clocks/checks prove no more
than 16 operations, remaining timeout propagation, no dispatch after exhaustion,
and no late healthy result. Concrete HTTP/TCP helper tests preserve status,
redirect refusal, capped samples without overflow failure and connect-only PG.
Actual Hello SDK/legacy routes agree on UNKNOWN versus readiness503; liveness is
independent. These are cooperative checkpoint laws, not cancellation/DNS timing
or SQL/provider acceptance evidence.
