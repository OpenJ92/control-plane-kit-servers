Source: [products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py](../../../../../../products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This stdlib process reads one fixed active upstream at startup and forwards
GET, POST, PUT, PATCH and DELETE requests by concatenating its URL with the
incoming path. Only the exact GET /health/live path is answered locally.
Changing a graph edge does not mutate these settings inside a running process;
the outer operations/runtime handoff owns target changes.

Environment parsing requires an HTTP(S) scheme and nonempty authority, strips
trailing slashes and range-checks PORT after int conversion. An empty mapping
falls back to os.environ. These checks do not authorize a destination, reject
all URL credentials/query forms or pin DNS. A malformed integer can raise
ValueError outside main's RouterConfigurationError handler. Direct dataclass
construction bypasses environment validation.

Forwarding drops Host, Connection and Content-Length, retaining other request
headers, including credentials. Responses return only status, body and
content-type. The opener disables redirects and uses a five-second timeout.
Successful upstream responses over 1 MiB become a fixed 502; HTTPError bodies
are instead read up to 1 MiB and returned with their status, so those can be
silently truncated. The generic caught forwarding failure hides exception text;
construction before the try and errors while handling HTTPError are outside
that catch.

The inbound body length is taken directly from Content-Length without a size
bound, and the threaded listener binds all interfaces without authentication,
TLS or an explicit inbound deadline. Suppressed access logging is not universal
exception redaction. There is no SDK control variable, retained history,
readiness probe or full reverse-proxy header policy here.

Related source and evidence: [products/http_active_router/product.cpk.json](../../../../../../products/http_active_router/product.cpk.json), [products/http_active_router/tests/test_http_active_router_product.py](../../../../../../products/http_active_router/tests/test_http_active_router_product.py), [scripts/http_active_router_image_smoke.sh](../../../../../../scripts/http_active_router_image_smoke.sh).
