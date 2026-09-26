Source: [dependencies.py](../../../../../../products/hello_server/src/control_plane_kit_servers_hello_server/dependencies.py).
Maintain with dependency semantics and bounds.

The existing DependencyCheck/environment naming language now lives independently
of the HTTP process. Input limits are explicit compatibility changes: 8 entries,
8192 UTF-8 declaration bytes, 64-character names, 128-character environment names,
2048 UTF-8 bytes per selected URL. Duplicate names/members and overflow reject
without truncation. DependencySnapshot copies only selected values into an
immutable mapping and hides them from repr. Missing URLs remain readiness failures.

One inspection checks at most 16 sequential HTTP/TCP operations. Before and after
each, it checks a five-second monotonic cooperative budget, passing at most two
seconds or remaining budget to blocking I/O. Budget exhaustion produces UNKNOWN
with fixed legacy503 text and no partial success or late HEALTHY. This is not a
DNS/socket cancellation or wall-clock return guarantee; there are no extra
threads, retries, cache or Operations deadline/history semantics.

HTTP refuses redirects, considers status and reads a capped 16,385-byte sample.
An oversized sample alone remains successful. Postgres checks only TCP connection,
never login/SQL. Failure text is bounded by finite validated names and fixed error
categories, without URL values. Unexpected exceptions are left for SDK's fixed
nonsemantic failure boundary. The same observation law feeds legacy and SDK paths.
