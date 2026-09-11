Source: [products/cpk_server/product.docker-cloudflare.cpk.json](../../../../products/cpk_server/product.docker-cloudflare.cpk.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This cpk-server-docker-cloudflare identity selects Docker runtime, Cloudflare
ingress and provider secret-material software over the shared CPK image.
Its public endpoints, four store requirements, Postgres secret reference and
ephemeral compute contract match the other variants.

The descriptor contains no Cloudflare API token, generated tunnel token,
hostname ownership or runtime delivery binding. Enabling named-ingress
software does not authorize tunnel/DNS creation or adopt retained resources;
the process uses separately admitted workspace operational truth and secret
references. Image-coordinate changes should update the shared lane without
collapsing the three product identities or inventing a separate build.

Related source and evidence: [products/cpk_server/product.cpk.json](../../../../products/cpk_server/product.cpk.json), [products/cpk_server/product.docker.cpk.json](../../../../products/cpk_server/product.docker.cpk.json), [products/cpk_server/tests/test_product_descriptor.py](../../../../products/cpk_server/tests/test_product_descriptor.py), [coordinates/server-products.json](../../../../coordinates/server-products.json), [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py).
