Source: [catalogue/products.json](../../../catalogue/products.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This descriptor catalogue assembles completed publication records with descriptor-byte hashes, product owner paths and image/source references. apply_coordinates.py derives it from the coordinate input plus current descriptor bytes; the package catalogue publisher then produces the installable catalogue and checksum sidecar. The three cpk-server variants are separate records over one build lane.

The completed marker is an admitted publication declaration, not fresh registry, health or deployment evidence. Reading this document does not register products in a running control plane. Keep it distinct from Core's decoded product catalogue and the topology client's desired-draft catalogue.

Related source and evidence: [coordinates/server-products.json](../../../coordinates/server-products.json), [scripts/apply_coordinates.py](../../../scripts/apply_coordinates.py), [src/control_plane_kit_servers/catalogue.py](../../../src/control_plane_kit_servers/catalogue.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py](../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py).
