Source: [scripts/product_image_coordinate.py](../../../scripts/product_image_coordinate.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This read-only selector loads the coordinate JSON and requires exactly one matching product. It renders an execution reference with the canonical SHA-256 digest, excluding the tag, or returns the separately validated source commit. It reads the supplied path and prints the selected coordinate through its CLI; it performs no pull, authentication or registry lookup.

Only the requested record and selected fields receive this helper's validation. Nonempty registry/repository text is not a comprehensive OCI-reference validator, and JSON/file errors are not all translated into ProductCoordinateError. Consumers must still verify image availability, platform and provenance under their own live-validation contract.

Related source and evidence: [coordinates/server-products.json](../../../coordinates/server-products.json), [tests/test_coordinates.py](../../../tests/test_coordinates.py), [scripts/http_active_router_published_image_smoke.sh](../../../scripts/http_active_router_published_image_smoke.sh).
