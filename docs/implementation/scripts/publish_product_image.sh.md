Source: [publish_product_image.sh](../../../scripts/publish_product_image.sh).

The existing closed producer cases retain their build/push/catalogue guidance.
The additional counter-witness case selects only the example Dockerfile, builds
explicit Linux/amd64, checks platform/UID10008 before push and reports genuine
post-push digest/image metadata. Its guidance records a witness on the governing
issue rather than updating production catalogue coordinates. Existing manual
workflow dispatch and package-write authority are unchanged; adding a case does
not authorize dispatch or upload.

For counter, capture the inspected built image ID before push and require the
tag still names it afterward. Select RepoDigests by the exact requested
repository prefix and require one canonical SHA256 reference. Missing or multiple
matches refuse; array ordering is not repository identity. The output associates
that exact reference with the captured image ID. This is producer metadata, not
a substitute for actual pulled-by-digest qualification.

The selection itself is delegated to `select_repository_digest.sh`, a pure
stdin-data helper exercised by the existing owning package suite. Image
inspection, push and built-ID correlation remain in this producer.

The producer rebuilds from selected source, so an earlier local/CI startup image
ID cannot identify its output. Publication approval must name reviewed source,
SDK/Core/base/dependencies, startup evidence, platform, exact destination/tag and
verified access/visibility, with actual pulled-digest qualification afterward.
No manifest digest is claimed before push. No credentials enter image/evidence.
