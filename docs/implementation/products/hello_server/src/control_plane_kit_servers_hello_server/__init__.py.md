Source: [products/hello_server/src/control_plane_kit_servers_hello_server/__init__.py](../../../../../../products/hello_server/src/control_plane_kit_servers_hello_server/__init__.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This product facade exports the dependency declaration type, configuration error and parsing/name helpers from server.py. Importing it loads that module's definitions and in-memory request-observation state, but the guarded main entrypoint does not start a listener. It is distinct from the shared Servers catalogue root; descriptor decoding does not need to import this process facade.

Related source and evidence: [products/hello_server/src/control_plane_kit_servers_hello_server/server.py](../../../../../../products/hello_server/src/control_plane_kit_servers_hello_server/server.py), [products/hello_server/tests/test_hello_server_product.py](../../../../../../products/hello_server/tests/test_hello_server_product.py).
