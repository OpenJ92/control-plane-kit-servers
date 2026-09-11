Source: [scripts/http_active_router_image_smoke.sh](../../../scripts/http_active_router_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This Docker smoke optionally builds the router, creates a fixed-name network
and synthetic Python upstream, publishes the router on loopback, waits for its
local liveness path and compares one forwarded GET response with a fixed
expected body. A passed run witnesses this image/request path, not a runtime
target transition or public CPK operation.

Pre-run and EXIT cleanup forcibly remove fixed container names and the network,
suppressing errors without checking ownership identities or final absence.
The project labels do not govern those removal calls. Readiness retries are
counted, but curl, Docker calls and failure log reads have no explicit deadline
or log bound here. Source builds and use of a caller-provided image remain
distinct; skipping a build alone does not admit an immutable image.

Related source and evidence: [products/http_active_router/Dockerfile](../../../products/http_active_router/Dockerfile), [products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py](../../../products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py), [scripts/http_active_router_published_image_smoke.sh](../../../scripts/http_active_router_published_image_smoke.sh).
