Source: [.github/workflows/tests.yml](../../../../.github/workflows/tests.yml).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This workflow runs the owning test.sh on main/develop pushes, all pull requests and manual dispatch. It grants contents/packages read, authenticates to GHCR before the gate and limits the job to thirty minutes. Checkout/login use version-tagged actions; the script determines the actual package, image and local-runtime work.

Read permission for registry access does not make the whole job free of local Docker effects. Cancellation of an earlier run in the same workflow/ref group is not a successful cleanup or test result. The separate publish workflow owns registry writes.

Related source and evidence: [test.sh](../../../../test.sh), [.github/workflows/publish-product-image.yml](../../../../.github/workflows/publish-product-image.yml), [tests/test_docker_harness.py](../../../../tests/test_docker_harness.py).
