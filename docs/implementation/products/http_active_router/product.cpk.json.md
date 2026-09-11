Source: [products/http_active_router/product.cpk.json](../../../../products/http_active_router/product.cpk.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This server product exposes HTTP provider internal on port 8000 and requires
one HTTP active socket whose value becomes ACTIVE_TARGET_URL. It carries no
secret deliveries, configuration artifacts or retained data; compute is
ephemeral. The process consumes its selected URL at startup. Runtime target
mutation is explicitly an operations/interpreter handoff.

The health-checkable capability names a bounded HTTP liveness check, not proof
that the active upstream works. Image digest/provenance fields are publication
coordinates; decoding or instantiating this value neither starts a router nor
verifies registry bytes. The process has no CPK control API or authorization
layer, so the surrounding topology owns exposure and trusted routing inputs.

Related source and evidence: [products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py](../../../../products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py), [products/http_active_router/tests/test_http_active_router_product.py](../../../../products/http_active_router/tests/test_http_active_router_product.py), [coordinates/server-products.json](../../../../coordinates/server-products.json).
