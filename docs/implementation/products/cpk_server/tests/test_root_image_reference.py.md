Source: [products/cpk_server/tests/test_root_image_reference.py](../../../../../products/cpk_server/tests/test_root_image_reference.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This pure string-comparison suite protects exact image-reference matching
without Docker or registry I/O. It allows the four supported Docker Hub
official-library spellings for the same repository and digest.

Negative cases reject empty observations, digest-only values, mutable tags,
different digests/repositories, foreign registries and malformed suffixes.
GHCR product references match only exactly; shortened repository aliases are
refused. These cases establish spelling equivalence, not image provenance,
registry bytes or runtime identity.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py).
