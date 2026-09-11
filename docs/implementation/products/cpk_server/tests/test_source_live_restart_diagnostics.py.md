Source: [products/cpk_server/tests/test_source_live_restart_diagnostics.py](../../../../../products/cpk_server/tests/test_source_live_restart_diagnostics.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

Fake Docker containers and a patched clock exercise rejection after transient
running and success after a continuous running interval with changed StartedAt.
The fake enforces the stop timeout. A separate assertion fixes the public
gateway policy at five attempts, five-second timeout and two-second interval.

The readiness failure test replaces network/HTTP dependencies and checks the
selected container projection retains exit status while excluding environment,
command, labels and State.Error fixture material. It is not universal redaction:
the source projection includes names, network addresses and timestamps, and the
readiness helper can include raw response/error text. Those fields are not all
size-bounded by this fixture.

No Docker restart, application-health check, real DNS request or persistence
recovery occurs in these tests. Running stability is distinct from readiness.

Controller owner: [source-live controller](../../../../../scripts/cpk_server_secret_provider_source_live.py).
