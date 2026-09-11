Source: [products/hello_server/product.cpk.json](../../../../products/hello_server/product.cpk.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This Core product descriptor declares Hello's internal HTTP socket/port, public greeting/palette/dependency defaults, health checks and ephemeral compute. It declares no secret deliveries or retained data. The published image/source coordinates and raw descriptor hash are synchronized through the coordinate/catalogue machinery.

The process can read optional dependency declarations, but this descriptor has no dynamic per-instance requirement sockets. That parameterization is explicitly a separate composition handoff. Declared health-check policies are interpreted elsewhere; decoding or instantiating the product performs no HTTP request and does not start Hello.

Related source and evidence: [products/hello_server/src/control_plane_kit_servers_hello_server/server.py](../../../../products/hello_server/src/control_plane_kit_servers_hello_server/server.py), [products/hello_server/tests/test_hello_server_product.py](../../../../products/hello_server/tests/test_hello_server_product.py), [scripts/apply_coordinates.py](../../../../scripts/apply_coordinates.py).
