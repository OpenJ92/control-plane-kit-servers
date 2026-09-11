Source: [products/hello_server/tests/test_hello_server_product.py](../../../../../products/hello_server/tests/test_hello_server_product.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests decode/instantiate the descriptor through the selected Core contract and exercise the local stdlib handler on a temporary loopback server. They compare escaped HTML/content headers, health/dependency responses and palette rejection before listening. Separate cases check dependency names, environment-only descriptors and bounded method/path observation helper behavior.

Some dependency checks are protected by source markers rather than live HTTP/database failure exercises. The observer negative test calls the recording helper directly with query material; it does not claim the public handler accepts every queried path. Descriptor/Dockerfile/hash checks do not pull the published image or prove deployment acceptance.

Related source and evidence: [products/hello_server/src/control_plane_kit_servers_hello_server/server.py](../../../../../products/hello_server/src/control_plane_kit_servers_hello_server/server.py), [products/hello_server/product.cpk.json](../../../../../products/hello_server/product.cpk.json), [scripts/hello_server_image_smoke.sh](../../../../../scripts/hello_server_image_smoke.sh).
