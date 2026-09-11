Source: [scripts/postgres_server_image_smoke.sh](../../../scripts/postgres_server_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This standalone fixture starts the selected PostgreSQL image with a named temporary data volume, waits with pg_isready and executes SELECT 1 through docker exec/psql. It proves only that selected local container path, not the product's remote password-authenticated verification transport or persistence across restart. The fixture password comes from an override or a test default and is passed in process/container environment.

Pre/EXIT cleanup force-removes fixed container and volume names while suppressing errors, without exact-ID/ownership checks or final absence verification. The retained-test-data label does not make those deletes generally safe for existing data. Failure logs are not explicitly byte-capped, and individual Docker/psql calls have no separate deadline. This historical fixture is not an authorization to delete retained application data.

Related source and evidence: [products/postgres_server/product.cpk.json](../../../products/postgres_server/product.cpk.json), [products/postgres_server/tests/test_postgres_server_product.py](../../../products/postgres_server/tests/test_postgres_server_product.py), [AGENTS.md](../../../AGENTS.md).
