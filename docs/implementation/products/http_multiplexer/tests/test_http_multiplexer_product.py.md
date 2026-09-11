Source: [products/http_multiplexer/tests/test_http_multiplexer_product.py](../../../../../products/http_multiplexer/tests/test_http_multiplexer_product.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests check canonical Core product bytes, primary/optional-observer socket
bindings, process-free instantiation and selected environment examples. Local
recording HTTP servers exercise the forward_primary and deliver_observers
helpers separately, checking copied POST content and the primary body.

An unavailable observer demonstrates the helper's categorical failure result;
a mocked exception ensures its supplied secret/address text is excluded.
These calls do not exercise the full HTTP handler ordering or prove
asynchronous delivery. Source-string checks name response caps, no-redirect
and failure behavior without testing every overflow/redirect case. Dockerfile
assertions establish wiring intent, not actual image/user execution. Local
servers are closed in finally; the descriptor digest test hashes descriptor
bytes, not registry image bytes.

Related source and evidence: [products/http_multiplexer/product.cpk.json](../../../../../products/http_multiplexer/product.cpk.json), [products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py](../../../../../products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py), [scripts/http_multiplexer_image_smoke.sh](../../../../../scripts/http_multiplexer_image_smoke.sh).
