Source: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/__init__.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/__init__.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This facade eagerly re-exports the gateway configuration/target/app/direct
probe API and Ed25519 verifier/replay/error values from their owners. Importing
it loads server and verification dependencies but does not invoke main or bind
a listener.

execute_probe is a direct trusted-call effect function; importing or calling
it does not perform the HTTP route's capability verification. Callers choosing
that API own its authorization boundary. Product descriptor consumption uses
Core values separately and need not import this facade.

Related source and evidence: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py), [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py), [products/cpk_local_gateway/product.cpk.json](../../../../../../products/cpk_local_gateway/product.cpk.json), [products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py](../../../../../../products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py).
