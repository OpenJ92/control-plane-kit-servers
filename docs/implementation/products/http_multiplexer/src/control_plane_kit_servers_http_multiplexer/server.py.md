Source: [products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py](../../../../../../products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This stdlib process captures one primary and up to two environment-configured
observer URLs at startup. For supported methods it first obtains the primary
response, then synchronously sends the same method/path/body and selected
headers to each observer, and finally sends the primary result to the caller.
Observers are sequential, not detached: their failures do not replace a
successful primary response, but their latency delays it.

The opener rejects redirects and reads at most cap+1 bytes, rejecting overflow:
1 MiB for primary responses and 16 KiB for observers, with a five-second timeout
per open. A primary HTTP error, redirect or other caught failure produces a
fixed 502 and skips observer delivery. Observer failures become categorical
indexed strings returned by deliver_observers; the HTTP handler discards that
tuple. There is no durable delivery record, retry or exactly-once guarantee.

Only Host, Connection and Content-Length are removed from outgoing headers.
Authorization and other incoming headers can reach observers along with the
body. URL parsing checks HTTP(S) and a nonempty authority, not a destination
grant, credential prohibition or DNS pin. An empty supplied mapping falls back
to the process environment; malformed integer PORT can escape main's
configuration-error catch, and direct settings construction bypasses that
environment validation.

The exact GET /health/live path is local; it does not probe any target. The
threaded process binds all interfaces, with no authentication/TLS, SDK control
surface, explicit incoming body bound or inbound deadline. Settings are fixed
for the process lifetime. Suppressed access logs and categorical forwarding
errors are specific mechanisms, not universal payload/exception redaction.

Related source and evidence: [products/http_multiplexer/product.cpk.json](../../../../../../products/http_multiplexer/product.cpk.json), [products/http_multiplexer/tests/test_http_multiplexer_product.py](../../../../../../products/http_multiplexer/tests/test_http_multiplexer_product.py), [scripts/http_multiplexer_image_smoke.sh](../../../../../../scripts/http_multiplexer_image_smoke.sh).
