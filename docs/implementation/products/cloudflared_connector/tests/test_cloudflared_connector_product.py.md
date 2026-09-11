Source: [products/cloudflared_connector/tests/test_cloudflared_connector_product.py](../../../../../products/cloudflared_connector/tests/test_cloudflared_connector_product.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite checks Core codec round-trip/instantiation, absent workload/retained surfaces, intentional runtime-generated token handoff and the owned wrapper's command/provenance declarations. Catalogue hash agreement is local byte-consistency evidence.

The test reads source/descriptor text and does not call Cloudflare, inspect the base image or start a tunnel. Empty descriptor secret deliveries must remain distinguishable from absence of a runtime credential requirement.

Related source and evidence: [products/cloudflared_connector/product.cpk.json](../../../../../products/cloudflared_connector/product.cpk.json), [products/cloudflared_connector/Dockerfile](../../../../../products/cloudflared_connector/Dockerfile).
