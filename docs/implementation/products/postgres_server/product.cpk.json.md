Source: [products/postgres_server/product.cpk.json](../../../../products/postgres_server/product.cpk.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This data-service descriptor wraps the digest-selected official PostgreSQL image without adding CPK schemas or migrations. It declares a private PostgreSQL provider, public database/user names, secret-reference password delivery and a retained data resource mounted at the image's data directory. Compute remains ephemeral; retained classification must survive compute teardown in the runtime owner.

Its semantic verification is the closed SELECT 1 check with referenced password authentication, not TCP reachability. The descriptor carries no password bytes and performs no query, volume creation or migration. Image initialization and runtime secret/data interpretation remain external owners; declaring retention is not authority to erase the volume.

Related source and evidence: [products/postgres_server/tests/test_postgres_server_product.py](../../../../products/postgres_server/tests/test_postgres_server_product.py), [scripts/postgres_server_image_smoke.sh](../../../../scripts/postgres_server_image_smoke.sh), [coordinates/server-products.json](../../../../coordinates/server-products.json).
