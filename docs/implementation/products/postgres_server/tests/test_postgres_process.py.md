Source: [test_postgres_process.py](../../../../../products/postgres_server/tests/test_postgres_process.py).

The product-owned suite covers process coordination, readiness observation,
failure reporting and image definition. Refused-lock-PID diagnostics are tested
at both the pure parser and existing failure entry point: printable ASCII,
decimal bounds, missing/duplicate/malformed hints, byte/line truncation and
unavailable logs remain closed states. Output excludes raw paths and messages.
A parser exception still propagates the original assertion through main's
borrowed-image and fixture cleanup; diagnostics never produce qualification PASS.
These tests do not simulate or diagnose PostgreSQL's lock ownership algorithm.
