Source: [scripts/product_image_lane.py](../../../scripts/product_image_lane.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This report builder reads a product inventory and classifies each entry as a present/missing local Dockerfile definition or a declared external OCI image. It resolves local paths from the inventory's parent repository coordinate and checks existence; external declarations are checked for the @sha256: marker. Neither check builds, pulls or inspects an image.

The resulting product-image-definitions-present status is a structural inventory result, not canonical digest validation, source parity, runtime readiness or successful publication. The report retains the supplied product entries. Treat the inventory as repository-owned input rather than a public redacted payload.

Related source and evidence: [scripts/run_all_tests.py](../../../scripts/run_all_tests.py), [tests/test_docker_harness.py](../../../tests/test_docker_harness.py).
