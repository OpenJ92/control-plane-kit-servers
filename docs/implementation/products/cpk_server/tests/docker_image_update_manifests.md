Evidence: [docker_image_update_manifests](../../../../../products/cpk_server/tests/docker_image_update_manifests).

The five files are ORIGINAL raw manifests captured through existing authenticated
`docker buildx imagetools inspect --raw` metadata reads. Their names are the exact
SHA-256 manifest coordinates already selected by `docker_image_update_images.json`.
The bytes were independently rehashed by Meridian and Kepler; no reserialization,
image rebuild, publication, layer pull/load or fixture-coordinate change occurred.

All five use Docker schema2 single-platform manifest/config media types. Each
manifest config.digest equals the unchanged historical fixture `image_id`. Four
have eight layers and pause has one. Fixed roles resolve through their exact
existing reference/digest; optional manual entries cannot overwrite this evidence.

These bytes are immutable linkage evidence for the #191 qualifier, not backend
classification, independently hashed config blobs/layers, cache availability,
startup or runtime acceptance. Raw runtime instance IDs and credentials are absent.
