Source: [products/http_active_router/Dockerfile](../../../../products/http_active_router/Dockerfile).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This image copies only the active-router process source onto a tagged Python
stdlib base. It creates the router account with UID 10003, selects that account
by name, sets PYTHONPATH and PORT, and launches the product module. No CPK or
SDK package is installed by this file.

The upstream URL is a runtime requirement, not an image default. EXPOSE 8000
declares container metadata without publishing a host port. The base tag and
this build recipe do not prove the immutable descriptor image was built from
the current checkout; image publication and execution are separate evidence.

Related source and evidence: [products/http_active_router/product.cpk.json](../../../../products/http_active_router/product.cpk.json), [products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py](../../../../products/http_active_router/src/control_plane_kit_servers_http_active_router/server.py), [products/http_active_router/tests/test_http_active_router_product.py](../../../../products/http_active_router/tests/test_http_active_router_product.py).
