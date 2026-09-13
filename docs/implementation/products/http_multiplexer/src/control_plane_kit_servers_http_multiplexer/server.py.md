Source: [server.py](../../../../../../products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py).
Maintain with protected host composition and primary/observer effects.

Forwarding helpers and application handler semantics are unchanged. Primary
exceptions become fixed502 before observers; after success, observers run
sequentially and ordinary failures permit later observers. Primary response wins.
Observer errors are bounded tuples currently discarded by the handler, not durable
history. Fail-open can add latency. Router HTTPError handling is different, so no
router forwarding code is imported. Per-call response/timeout/no-redirect/header
rules remain; no whole-server body/concurrency hardening is claimed.

Factory validates before socket creation, uses the exact unbound standard server,
installs SDK, then binds/activates. Close follows construction failure and every
serve exit, preserving the clean main KeyboardInterrupt return. SDK owns reserved
protocol/authentication, with separate per-instance static/health holders and no
commands/variables/replay store. Liveness is HEALTHY with no primary/observer call;
readiness=None. Canonical undeclared readiness differs from unknown reserved ready;
both stay inside SDK. Ordinary /health/ready still multiplexes application auth.
No extra listener, supervisor, readiness probe or target switching is added.
