Source: [tests/test_docker_harness.py](../../../tests/test_docker_harness.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

Most cases inspect gate, workflow, Dockerfile and publication-script text for selected wiring and the absence of broad cleanup commands. One subprocess runs the structural product-image-lane reporter against repository inventory and asserts its declared products/build definitions. That report does not launch those images.

The tests distinguish current CI registry-read setup from the publication workflow's registry-write permission. The residue checks confirm the script's selected label/query vocabulary, not real resource absence or cleanup correctness. A source-marker assertion must not be promoted into a provider or end-to-end gate witness.

Related source and evidence: [test.sh](../../../test.sh), [scripts/run_all_tests.py](../../../scripts/run_all_tests.py), [scripts/product_image_lane.py](../../../scripts/product_image_lane.py), [scripts/docker_residue_audit.sh](../../../scripts/docker_residue_audit.sh).
