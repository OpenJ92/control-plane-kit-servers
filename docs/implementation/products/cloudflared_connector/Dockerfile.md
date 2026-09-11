Source: [products/cloudflared_connector/Dockerfile](../../../../products/cloudflared_connector/Dockerfile).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This small owned wrapper selects an exact upstream cloudflared base digest and fixes ENTRYPOINT to cloudflared with no-autoupdate and CMD to tunnel run. It closes the command-shape gap recorded by the product tests. The file contains no tunnel token or API credential and does not create DNS/tunnel resources during build.

Actual upstream binary behavior, inherited user/filesystem and runtime-delivered token handling are separate contracts of the selected base and interpreter. Do not infer a newly verified base implementation, numeric identity or successful tunnel from these two command declarations.

Related source and evidence: [products/cloudflared_connector/product.cpk.json](../../../../products/cloudflared_connector/product.cpk.json), [products/cloudflared_connector/tests/test_cloudflared_connector_product.py](../../../../products/cloudflared_connector/tests/test_cloudflared_connector_product.py).
