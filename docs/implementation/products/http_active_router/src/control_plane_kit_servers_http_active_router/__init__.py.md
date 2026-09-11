Source: [products/http_active_router/src/control_plane_kit_servers_http_active_router/__init__.py](../../../../../../products/http_active_router/src/control_plane_kit_servers_http_active_router/__init__.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This facade imports and exports the process settings, configuration error and
main entrypoint. Importing it loads the stdlib server module but does not call
main or bind a listener. Descriptor decoding belongs to the separate catalogue/
Core value path and does not need this process facade.

Related source and evidence: [products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py](../../../../../../products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py), [products/http_active_router/tests/test_http_active_router_product.py](../../../../../../products/http_active_router/tests/test_http_active_router_product.py).
