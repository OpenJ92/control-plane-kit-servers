Source: [products/cpk_server/product.docker.cpk.json](../../../../products/cpk_server/product.docker.cpk.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This distinct cpk-server-docker product identity uses the same CPK image and
HTTP/MCP/store/lifecycle contract as the base descriptor. Its meaningful public
selections enable the Docker runtime interpreter and provider material resolver,
while ingress interpreters remain disabled.

Those selections make software available to the process. They do not supply a
Docker endpoint, socket mount, client certificate, provider credential or
workspace grant. Runtime authority and delivery are separately admitted
operational values. The declared Postgres secret reference is not that runtime
authority. Keep the shared image coordinate synchronized through repository
coordinates while preserving each variant's identity and environment policy.

Related source and evidence: [products/cpk_server/product.cpk.json](../../../../products/cpk_server/product.cpk.json), [products/cpk_server/product.docker-cloudflare.cpk.json](../../../../products/cpk_server/product.docker-cloudflare.cpk.json), [products/cpk_server/tests/test_product_descriptor.py](../../../../products/cpk_server/tests/test_product_descriptor.py), [coordinates/server-products.json](../../../../coordinates/server-products.json), [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py).
