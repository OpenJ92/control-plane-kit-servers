Source: [scripts/apply_coordinates.py](../../../scripts/apply_coordinates.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

## Local generation boundary

This script admits the coordinate input and prepares replacements for dependency pins, selected product Dockerfiles, product descriptor image fields and the source descriptor catalogue. generate_updates reads repository files and returns a path-to-bytes update map; it is not a pure transform of the coordinate mapping alone. Descriptor bodies are deep-copied and only their image coordinates plus existing source-commit provenance fields are rewritten. Raw rewritten bytes determine the catalogue descriptor hashes.

Default CLI execution writes those files sequentially, then invokes the catalogue publisher to write packaged metadata and its sidecar. This is local multi-file mutation without an atomic transaction or rollback. --check compares only the generated update map with current files; it does not call publish_catalogue or independently check every packaged output. The separate catalogue tests own that additional surface.

## Admission and evidence limits

load_coordinates checks the schema, unique product IDs, canonical source commits/digests and relative paths without parent traversal. It is not a complete filesystem containment or symlink defense, registry verifier or source-to-image provenance attestor. Dependency replacement targets the specific existing URL shapes; it does not discover every potential dependency reference. Status completed in generated catalogue rows reflects the input convention, not a provider observation.

Changes to the coordinate language or descriptor representation must preserve the generator's byte/hash relationship and actual consumer pins. Run this effectful CLI only through the repository's authorized workflow; documentation authoring does not execute it.

Related source and evidence: [coordinates/server-products.json](../../../coordinates/server-products.json), [catalogue/products.json](../../../catalogue/products.json), [src/control_plane_kit_servers/catalogue.py](../../../src/control_plane_kit_servers/catalogue.py), [tests/test_coordinates.py](../../../tests/test_coordinates.py), [tests/test_descriptor_catalogue.py](../../../tests/test_descriptor_catalogue.py).
