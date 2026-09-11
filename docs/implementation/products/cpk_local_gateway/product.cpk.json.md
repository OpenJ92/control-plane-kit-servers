Source: [products/cpk_local_gateway/product.cpk.json](../../../../products/cpk_local_gateway/product.cpk.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This is the external container-product value for cpk-local-gateway revision 1,
consumed through Core's product codec without importing the process. It names
an OCI digest and historical provenance, not freshly verified registry bytes
or a claim that the current source produced that digest.

The control HTTP provider is port 8000. Optional target-http and target-postgres
requirements use runtime-control bindings without environment address
assignments. The Postgres requirement owns a conditional POSTGRES_PASSWORD
secret-reference delivery; there is no unconditional product-level secret
delivery. Compilation tests show that the delivery exists with the Postgres
edge and disappears without it. This describes desired delivery, not actual
secret resolution or revocation of a running process.

The public target-map default is empty, health checks are live/ready HTTP,
compute is ephemeral and there are no retained mounts. Target material and
verification keys must be supplied by the composition/runtime boundary.
Descriptor health only observes the minimal process routes; it does not prove
private-target health, signed-probe access or provider convergence.

Related source and evidence: [products/cpk_local_gateway/Dockerfile](../../../../products/cpk_local_gateway/Dockerfile), [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py](../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py), [products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py](../../../../products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py), [catalogue/products.json](../../../../catalogue/products.json).
