Source: [scripts/cpk_local_gateway_structural_grant_image_smoke.sh](../../../scripts/cpk_local_gateway_structural_grant_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This wrapper runs the mounted structural-grant Python check inside a gateway
image. By default it reads the product descriptor using host Python, selects
registry/repository@digest and pulls it. CPK_LOCAL_GATEWAY_IMAGE overrides that
coordinate; CPK_LOCAL_GATEWAY_STRUCTURAL_BUILD_SOURCE=1 instead builds the
current Dockerfile, using an override or a local source tag.

docker run replaces the entrypoint, mounts only the check file read-only and
requests container removal on exit. It does not launch the server, publish
ports, verify live probes or supply a provider history record. Source-build
mode is not published-digest evidence, and an arbitrary image override is not
automatically immutable. Build/pull/run effects have no global timeout,
explicit container name/trap recovery or removal verification in this wrapper.
Its presence is documentation of apparatus, not a new execution authorization.

Related source and evidence: [scripts/cpk_local_gateway_structural_grant_check.py](../../../scripts/cpk_local_gateway_structural_grant_check.py), [products/cpk_local_gateway/Dockerfile](../../../products/cpk_local_gateway/Dockerfile), [products/cpk_local_gateway/product.cpk.json](../../../products/cpk_local_gateway/product.cpk.json).
