Source: [products/secrets_server/tests/test_secrets_server_product.py](../../../../../products/secrets_server/tests/test_secrets_server_product.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These package tests decode and canonically round-trip the Secrets descriptor
through the selected Core product contract. They check product identity/family,
the HTTP control port, retained provider-data mount, empty recursive inputs and
ordinary instantiation without importing the provider implementation.

Other assertions inspect bootstrap declarations, Dockerfile/entrypoint text and
selected image-smoke strings: numeric UID, provider source pin, protected paths,
restart call sites and delegation operations. They establish repository wiring,
not actual image execution, file ownership, authentication, restart survival or
successful cleanup. The executable witnesses own those observations.

Keep contract changes coordinated with the product declaration and bootstrap
owner. A matching string in the smoke script does not certify that its branch
ran or that every external request and cleanup outcome was successful.

Related source and evidence: [products/secrets_server/product.cpk.json](../../../../../products/secrets_server/product.cpk.json), [products/secrets_server/bootstrap.contract.json](../../../../../products/secrets_server/bootstrap.contract.json), [products/secrets_server/tests/live_numeric_bootstrap.py](../../../../../products/secrets_server/tests/live_numeric_bootstrap.py), [scripts/secrets_server_image_smoke.sh](../../../../../scripts/secrets_server_image_smoke.sh), [coordinates/server-products.json](../../../../../coordinates/server-products.json).
