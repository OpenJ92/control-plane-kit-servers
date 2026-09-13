Source: [server.py](../../../../../../products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py).
Maintain with router process composition and forwarding.

Forwarding and ordinary application handlers retain their prior semantics.
Factory composition uses exact standard ThreadingHTTPServer, unbound, with the
SDK installed before bind/activate. SDK keeps protected requests inside the
reserved namespace before any application do-method; no SDK admission code is
copied. Separate static and health holders/verifiers capture immutable local
identity, issuer/audience and keys. The sole liveness callback returns HEALTHY
without upstream work; readiness=None. No commands, variables, cache or switching.

Canonical control paths end in liveness/readiness. Undeclared readiness is not
the same test as unknown /__control/health/ready; both remain zero-forward.
Ordinary /health/ready forwards, including ordinary application authorization.
Liveness says only that the configured local process handles the request.

Invalid configuration or production port fails before socket creation. Construction
failures close the socket, and serving always closes in finally. KeyboardInterrupt
retains the clean exit behavior. Tests join their host thread and workers; no
same-thread shutdown, process supervisor or new listener is introduced. Application
request bodies/concurrency and existing HTTP-error handling are not rewritten as
whole-server hardening. No durable mutation/history or provider action is owned here.
