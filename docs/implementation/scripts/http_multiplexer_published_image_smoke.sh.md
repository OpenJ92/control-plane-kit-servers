Source: [scripts/http_multiplexer_published_image_smoke.sh](../../../scripts/http_multiplexer_published_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This wrapper resolves the multiplexer digest image reference from the coordinate manifest,
pulls it and calls the ordinary smoke with building disabled. It inherits that
smoke's fixture mutations, loopback exposure and fixed-name cleanup. The
coordinate helper selects metadata rather than independently proving registry
provenance, runtime identity or complete observer delivery.

Its current host python3 invocation is inconsistent with the maintained
Docker-only validation rule. Reconcile the authorized execution path and its
prerequisites before use; this companion grants no host fallback or permission
to remove existing resources.

Related source and evidence: [scripts/product_image_coordinate.py](../../../scripts/product_image_coordinate.py), [scripts/http_multiplexer_image_smoke.sh](../../../scripts/http_multiplexer_image_smoke.sh), [products/http_multiplexer/product.cpk.json](../../../products/http_multiplexer/product.cpk.json), [AGENTS.md](../../../AGENTS.md).
