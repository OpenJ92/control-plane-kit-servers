Source: [products/hello_server/Dockerfile](../../../../products/hello_server/Dockerfile).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This product image copies only Hello source and runs its stdlib module under the hello account with numeric UID10002. Environment defaults supply greeting, palette and an empty dependency list. EXPOSE declares the container port; it does not publish a host listener. The process itself binds its configured port when started.

The Python base is selected by tag, not digest here. Product publication records the built image digest separately. Changing process defaults, user identity or source layout requires checking descriptor and image tests, rather than assuming the old published artifact changes with the Dockerfile.

Related source and evidence: [products/hello_server/src/control_plane_kit_servers_hello_server/server.py](../../../../products/hello_server/src/control_plane_kit_servers_hello_server/server.py), [products/hello_server/product.cpk.json](../../../../products/hello_server/product.cpk.json), [products/hello_server/tests/test_hello_server_product.py](../../../../products/hello_server/tests/test_hello_server_product.py).
