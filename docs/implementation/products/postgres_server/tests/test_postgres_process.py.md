Source: [test_postgres_process.py](../../../../../products/postgres_server/tests/test_postgres_process.py).

The product-owned suite covers process coordination, readiness observation,
failure reporting and image definition. Refused-lock-PID diagnostics are tested
at both the pure parser and existing failure entry point: printable ASCII,
decimal bounds, missing/duplicate/malformed hints, byte/line truncation and
unavailable logs remain closed states. Output excludes raw paths and messages.
A parser exception still propagates the original assertion through main's
borrowed-image and fixture cleanup; diagnostics never produce qualification PASS.
These tests do not simulate or diagnose PostgreSQL's lock ownership algorithm.

Role-diagnostic targets exercise the existing coordinator, main and bounded
failure entry point. A controlled existing management thread proves that role
observations precede cleanup while lifecycle failure remains unchanged. Tests
keep entrypoint-child and native-emitter identities separate, retain ended or
missing states, and cover bounded malformed/duplicate/truncated/unavailable
records, nullable fields, redacted identity and output failure. The focused red
establishes absent reporting only. Neither fake role numbers nor a prospective
green prove the historic refused PID's owner.

Acquisition failures explicitly produce nullable PID/state fields. A failed whole
capture clears its prior snapshot, and role-property access shares the existing
best-effort emitter boundary. Targets verify that absent role or source identity
does not replace the primary lifecycle failure or erase independently available
fields. The normal package-integrity scan remains required alongside this focused
suite; the focused launch route does not execute that preflight.
