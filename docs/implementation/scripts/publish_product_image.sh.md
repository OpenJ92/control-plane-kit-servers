Source: [scripts/publish_product_image.sh](../../../scripts/publish_product_image.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This effectful shell script selects a supported product Dockerfile, checks local coordinate consistency in the policy container, builds a tagged image from the checkout and pushes it to GHCR. It then prints the first local RepoDigest and instructs the caller to update coordinates and validate separately. It does not itself rewrite catalogue metadata, attest source-to-image identity, read back private registry bytes or run the full package suite.

The case statement names build lanes, including base cpk-server; descriptor variant IDs and the external PostgreSQL product are not separate supported build choices. OWNER/PACKAGE/TAG and the selected checkout determine the destination/artifact. Registry authentication is supplied externally. A failure after push does not undo publication, and the script has no cleanup or rollback transaction. Its local digest output is weaker evidence than authenticated verification of the exact approved registry artifact.

This companion grants no publication authority. The previously approved image upload used its own exact artifact/destination evidence; source availability of this broader build-and-push script does not authorize rebuilding it.

Related source and evidence: [.github/workflows/publish-product-image.yml](../../../.github/workflows/publish-product-image.yml), [scripts/apply_coordinates.py](../../../scripts/apply_coordinates.py), [coordinates/server-products.json](../../../coordinates/server-products.json).
