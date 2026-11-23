Source: [test_http_sample_admission.py](../../../../../products/cpk_server/tests/test_http_sample_admission.py).
Maintain alongside the product's receiver binding and real startup path.

The first test compares the opt-in and ordinary runtime contracts in all
three CPK variants. The ready check names the HTTP socket even though both
HTTP and MCP use 8080. A different receiver at the same audience, a different
slot, malformed configuration and redirection of the named port are refused.

The second test enters the actual CPK main function. With a valid companion
it observes the configured app, ordinary readiness and protected sample route.
A misplaced, empty or malformed companion must fail before protected bootstrap,
credential verification, Operations or listener startup. The default product
suite and the named cohort qualifications exercise the same tests.
