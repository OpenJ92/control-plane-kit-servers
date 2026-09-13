Source: [coordinates/server-products.json](../../../coordinates/server-products.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This is the maintained input for upstream source pins and published product image/source coordinates. The three cpk-server descriptor variants share one image coordinate and implementation directory while retaining distinct product IDs and descriptor paths. A variant is not a separate build merely because it has its own descriptor.

The declared source commit, selected dependency commits and image digest are separate evidence coordinates. They must be updated through actual reviewed adoption/publication, not inferred from the current checkout or a moved tag. The coordinate helper renders registry/repository@digest for execution and discards the mutable tag for that purpose. This file contains declarations, not a registry query, image-account seal or proof that any deployment ran.

Related source and evidence: [scripts/apply_coordinates.py](../../../scripts/apply_coordinates.py), [scripts/product_image_coordinate.py](../../../scripts/product_image_coordinate.py), [tests/test_coordinates.py](../../../tests/test_coordinates.py).

Servers #193 selects Core/Operations `95452249d0340707a5cdffe737e34669e9d53165`, Interpreters #150/#151 merge `77c9a7f54e6d8ef886733c8ebd3476e796fad8ad`, and canonical `control_plane_kit_server_sdk_commit` `2b10d5a354ba4da9407d336703aacb96910100d4`. Interpreters and SDK select the same exact Core URL. The SDK field is a required canonical 40-character lowercase commit and controls the root SDK[verification] dependency; each product wrapper later adds its own generated installation destination.

The new Core contracts add optional health declarations and dedicated authority values; Operations source is unchanged across the previous e3e29995-to95452249 interval. No new interpreter transport, product behavior or authority follows from dependency availability. Secrets and all published image/product/source coordinates remain unchanged; source adoption does not select a new published image or resolve the held #163 attempt. The ordinary gate distinguishes installed candidate-source compatibility from old published-image baseline coexistence.
