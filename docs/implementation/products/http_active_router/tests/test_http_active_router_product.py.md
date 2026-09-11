Source: [products/http_active_router/tests/test_http_active_router_product.py](../../../../../products/http_active_router/tests/test_http_active_router_product.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests protect the selected Core descriptor's identity, canonical bytes,
HTTP socket/environment mapping, liveness policy and process-free
instantiation. A local recording HTTP server exercises the forward helper's
POST path/query/body and selected-header behavior; a mocked opener failure
checks the fixed response does not reveal the supplied exception material.

Startup examples test required/absolute upstream URLs and one valid port.
Other assertions inspect source strings and Dockerfile wiring for redirect,
response-cap and non-root intent. They do not behaviorally establish every
redirect/overflow case, HTTP handler input admission, registry provenance or
actual image identity. The descriptor SHA256 assertion hashes descriptor bytes,
not the image. Each local server is shut down in finally; these are package
tests, separate from the image smoke.

Related source and evidence: [products/http_active_router/product.cpk.json](../../../../../products/http_active_router/product.cpk.json), [products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py](../../../../../products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py), [scripts/http_active_router_image_smoke.sh](../../../../../scripts/http_active_router_image_smoke.sh).
