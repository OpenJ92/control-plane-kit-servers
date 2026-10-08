Source: [test_hello_dependencies.py](../../../../../products/hello_server/tests/test_hello_dependencies.py).

Boundary tests retain dependency semantics while exercising max/max+1 declaration,
name, URL and environment-name limits. Controlled clocks/checks prove no more
than 16 operations, remaining timeout propagation, no dispatch after exhaustion,
and no late healthy result. Concrete HTTP/TCP helper tests preserve status,
redirect refusal, capped samples without overflow failure and connect-only PG.
Actual Hello SDK readiness preserves UNKNOWN after budget exhaustion; SDK
liveness remains independent. #241 removes only legacy HTTP encoding assertions,
retaining the selected dependency callback, no-late-healthy and bounded-work laws.
These are cooperative checkpoint laws, not cancellation/DNS timing
or SQL/provider acceptance evidence.
