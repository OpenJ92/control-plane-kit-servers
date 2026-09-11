Source: [scripts/hello_server_published_image_smoke.sh](../../../scripts/hello_server_published_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This older wrapper reads the product descriptor with host python3, renders registry/repository@digest, pulls it and delegates to the Hello smoke with building disabled. It selects descriptor bytes rather than the newer coordinate helper, and performs no authenticated source-to-image or visibility verification.

The host-Python implementation is not permission to bypass the current Docker-only validation policy. Reconcile the actual invocation with the governing plan before execution. Child smoke cleanup/publication/timeout limits still apply, and the pulled image remains cached.

Related source and evidence: [products/hello_server/product.cpk.json](../../../products/hello_server/product.cpk.json), [scripts/hello_server_image_smoke.sh](../../../scripts/hello_server_image_smoke.sh), [AGENTS.md](../../../AGENTS.md).
