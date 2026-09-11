Source: [coordinates/server-products.json](../../../coordinates/server-products.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This is the maintained input for upstream source pins and published product image/source coordinates. The three cpk-server descriptor variants share one image coordinate and implementation directory while retaining distinct product IDs and descriptor paths. A variant is not a separate build merely because it has its own descriptor.

The declared source commit, selected dependency commits and image digest are separate evidence coordinates. They must be updated through actual reviewed adoption/publication, not inferred from the current checkout or a moved tag. The coordinate helper renders registry/repository@digest for execution and discards the mutable tag for that purpose. This file contains declarations, not a registry query, image-account seal or proof that any deployment ran.

Related source and evidence: [scripts/apply_coordinates.py](../../../scripts/apply_coordinates.py), [scripts/product_image_coordinate.py](../../../scripts/product_image_coordinate.py), [tests/test_coordinates.py](../../../tests/test_coordinates.py).
