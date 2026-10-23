Source: [products/postgres_server/Dockerfile](../../../../products/postgres_server/Dockerfile).
Maintain this companion alongside its source and selected dependencies.

The PostgreSQL source recipe retains its exact base image, installs Python and
the SDK verification extra, copies its product-owned process wrapper, and runs
as UID/GID 70 with the existing database and control ports. File-based password
and wrapper-configuration inputs remain deployment-owned; no credential is baked
into this recipe.

For #313, the existing coordinate generator updates only the SDK archive URL to
accepted merge `43838fd0f4391428cfffa87f8c4dbd5cc6d5eab1`, which selects accepted
Core `879efb9576ac0580a6236d0a7372c036537b4dfe`. Base image, package subset, user,
environment, entrypoint and ports are unchanged. The normal source-product gate
must prove build/composition compatibility; this recipe edit does not publish an
image or change historical product source/tag/digest/descriptor coordinates.
