Source: [products/http_multiplexer/product.cpk.json](../../../../products/http_multiplexer/product.cpk.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This server product has one required HTTP primary requirement and two optional
HTTP observer requirements, each mapped to its named URL environment variable.
Its internal HTTP provider is port 8000. No retained resources, secret
deliveries or configuration artifacts are declared; compute is ephemeral.

The primary owns the returned response and observers receive copies under the
process implementation's failure behavior. Optional sockets do not imply
durable delivery, independent authorization or asynchronous fan-out. The
single bounded liveness check only targets /health/live, not primary/observer
availability. Descriptor instantiation is a Core value transformation, not
process startup or published-image verification.

Related source and evidence: [products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py](../../../../products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py), [products/http_multiplexer/tests/test_http_multiplexer_product.py](../../../../products/http_multiplexer/tests/test_http_multiplexer_product.py), [coordinates/server-products.json](../../../../coordinates/server-products.json).
