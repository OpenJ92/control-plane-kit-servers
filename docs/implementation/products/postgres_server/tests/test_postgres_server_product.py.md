Source: [products/postgres_server/tests/test_postgres_server_product.py](../../../../../products/postgres_server/tests/test_postgres_server_product.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These Core-value tests preserve the official-image descriptor round trip, private protocol/port, secret rather than public password delivery, retained mount/lifecycle and SELECT 1 authentication contract. Instantiation proves a topology value can be formed without application/store logic.

They do not start PostgreSQL, authenticate a real connection, test restart retention or run a migration. The separate image smoke owns a narrower local database execution witness and must not be substituted for retained-data lifecycle acceptance.

Related source and evidence: [products/postgres_server/product.cpk.json](../../../../../products/postgres_server/product.cpk.json), [scripts/postgres_server_image_smoke.sh](../../../../../scripts/postgres_server_image_smoke.sh).
