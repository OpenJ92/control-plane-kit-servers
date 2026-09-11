Source: [scripts/http_active_router_published_image_smoke.sh](../../../scripts/http_active_router_published_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This wrapper asks product_image_coordinate for the active-router digest in the
coordinate manifest, pulls it and invokes the ordinary image smoke with building
disabled. This selects a published coordinate; the helper does not prove
registry provenance or independent image/account identity.

The wrapper currently invokes host python3, which conflicts with the maintained
Docker-only executable-validation rule. An authorized invocation must reconcile
that prerequisite rather than treating this note as permission for a host
fallback. All ordinary smoke network, loopback exposure and fixed-name cleanup
behavior is inherited.

Related source and evidence: [scripts/product_image_coordinate.py](../../../scripts/product_image_coordinate.py), [scripts/http_active_router_image_smoke.sh](../../../scripts/http_active_router_image_smoke.sh), [products/http_active_router/product.cpk.json](../../../products/http_active_router/product.cpk.json), [AGENTS.md](../../../AGENTS.md).
