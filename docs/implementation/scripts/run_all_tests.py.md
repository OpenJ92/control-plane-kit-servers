Source: [scripts/run_all_tests.py](../../../scripts/run_all_tests.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This in-image runner checks coordinates, compiles source/products/scripts/tests, discovers root tests and each owned product's tests, then emits the image-definition report. Product ownership is inferred for this discovery purpose from descriptors, source directories or Dockerfiles; an owned product without a tests directory fails instead of silently disappearing.

Each subprocess uses check=True and stages run serially. Relative command paths require the image's /app repository working directory even though discovery calculates an absolute ROOT. This runner does not include the outer test.sh's numeric-file, published-image or root-bootstrap witnesses, and its structural image-lane report does not build or run product images.

Related source and evidence: [test.sh](../../../test.sh), [Dockerfile.test](../../../Dockerfile.test), [scripts/product_image_lane.py](../../../scripts/product_image_lane.py), [tests/test_docker_harness.py](../../../tests/test_docker_harness.py).
