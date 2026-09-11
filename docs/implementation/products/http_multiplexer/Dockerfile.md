Source: [products/http_multiplexer/Dockerfile](../../../../products/http_multiplexer/Dockerfile).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This image copies the standalone multiplexer source onto the tagged Python
stdlib base, creates UID 10004's multiplexer account, selects it by name and
launches the module using PYTHONPATH. No CPK or SDK runtime is installed here.
PORT defaults to 8000; primary/observer addresses arrive through runtime
environment bindings.

EXPOSE does not publish a host port or add authentication/TLS. Rebuilding from
this source and running the descriptor's published digest are separate evidence
paths; neither the account name nor base tag is an independently checked
published-image identity.

Related source and evidence: [products/http_multiplexer/product.cpk.json](../../../../products/http_multiplexer/product.cpk.json), [products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py](../../../../products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py), [products/http_multiplexer/tests/test_http_multiplexer_product.py](../../../../products/http_multiplexer/tests/test_http_multiplexer_product.py).
