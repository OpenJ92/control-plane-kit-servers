Source: [scripts/http_multiplexer_image_smoke.sh](../../../scripts/http_multiplexer_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This Docker smoke optionally builds the multiplexer and starts fixed-name
primary and observer fixtures on its network. It publishes the multiplexer on
loopback, checks liveness, asserts the primary's fixed response body and polls
observer logs for the copied /anything request. A passed run is one fan-out
witness, not durable observer history, delivery under failure or public CPK
activity acceptance.

Pre-run and EXIT cleanup remove the fixed container/network names with errors
suppressed, without identity admission or a final absence check. Project
labels are attached but do not constrain those removals. Counted polling loops
do not bound individual curl/Docker commands or full log reads. Fixtures use a
tagged Python base, and disabling the product build does not independently
validate the caller's image coordinate.

Related source and evidence: [products/http_multiplexer/Dockerfile](../../../products/http_multiplexer/Dockerfile), [products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py](../../../products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py), [scripts/http_multiplexer_published_image_smoke.sh](../../../scripts/http_multiplexer_published_image_smoke.sh).
