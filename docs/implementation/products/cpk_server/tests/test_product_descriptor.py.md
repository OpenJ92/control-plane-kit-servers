Source: [products/cpk_server/tests/test_product_descriptor.py](../../../../../products/cpk_server/tests/test_product_descriptor.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite checks the three CPK descriptor identities and their distinct
interpreter selections, canonical Core encoding, direct HTTP/MCP/store sockets,
secret-reference-only delivery and current catalogue coordinates. It exercises
catalogue lookup plus negative descriptor/image-digest mismatches and unknown
descriptor fields using local files.

The variant tests distinguish interpreter software from authority and scan for
selected forbidden endpoint/credential strings. They do not authenticate a
runtime or prove a universal secret sanitizer. The image digest is compared
with coordinate metadata; no registry bytes are fetched here.

A fresh subprocess loads the catalogue and checks selected process/framework
modules are absent. That supports the lightweight data-loading path, not every
possible import combination. The packaged-catalogue checksum test verifies
local artifact bytes, not public registration, deployment readiness or
historical child acceptance.

Related source and evidence: [products/cpk_server/product.cpk.json](../../../../../products/cpk_server/product.cpk.json), [products/cpk_server/product.docker.cpk.json](../../../../../products/cpk_server/product.docker.cpk.json), [products/cpk_server/product.docker-cloudflare.cpk.json](../../../../../products/cpk_server/product.docker-cloudflare.cpk.json), [src/control_plane_kit_servers/catalogue.py](../../../../../src/control_plane_kit_servers/catalogue.py), [coordinates/server-products.json](../../../../../coordinates/server-products.json).
