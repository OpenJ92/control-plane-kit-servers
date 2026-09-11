Source: [products/secrets_server/product.cpk.json](../../../../products/secrets_server/product.cpk.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This canonical product value describes a data-service container with one HTTP
control provider on port 8081 and no requirement sockets. Compute is ephemeral;
provider-data is retained at /var/lib/cpk-secrets. Its image coordinate identifies
a published artifact separately from the external provider source provenance.

Secret deliveries, public environment and configuration artifacts are empty.
Root key and credential inputs belong to the adjacent non-recursive bootstrap
contract, not to secret values in this document. Instantiating the descriptor
creates topology data; it neither provisions custody nor starts the process.
The private-control description is an intended deployment boundary, not an
authentication or network isolation mechanism supplied by JSON.

The two HTTP checks expect 200 from live and ready endpoints with explicit
attempt, timing and evidence bounds for the verification interpreter. The
selected provider implements these as health responses; a ready response is
not a fresh database round trip, retained-data proof or parent custody receipt.
Changing the image, socket or mount contract requires checking the catalogue,
bootstrap composition and actual consumer pin together.

Related source and evidence: [products/secrets_server/bootstrap.contract.json](../../../../products/secrets_server/bootstrap.contract.json), [products/secrets_server/Dockerfile](../../../../products/secrets_server/Dockerfile), [coordinates/server-products.json](../../../../coordinates/server-products.json), [src/control_plane_kit_servers/catalogue.py](../../../../src/control_plane_kit_servers/catalogue.py), [products/secrets_server/tests/test_secrets_server_product.py](../../../../products/secrets_server/tests/test_secrets_server_product.py).
