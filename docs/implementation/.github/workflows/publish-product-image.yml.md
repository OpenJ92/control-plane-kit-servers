Source: [.github/workflows/publish-product-image.yml](../../../../.github/workflows/publish-product-image.yml).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This manually dispatched workflow checks out source, authenticates to GHCR using the workflow token and invokes publish_product_image.sh with product and tag inputs. It grants packages-write in addition to contents-read, so dispatch can create externally visible registry state. It does not run the ordinary owning test workflow before publication or update the coordinate catalogue afterward.

Action references are version tags. Dispatch inputs are interpolated into a shell command by the workflow; this file supplies no separate input-admission step before that interpolation. Review both this entrypoint and the script when changing accepted inputs, destinations or authentication. A workflow run is not by itself proof of private visibility, an approved artifact digest or immutable provenance.

Related source and evidence: [scripts/publish_product_image.sh](../../../../scripts/publish_product_image.sh), [.github/workflows/tests.yml](../../../../.github/workflows/tests.yml).
