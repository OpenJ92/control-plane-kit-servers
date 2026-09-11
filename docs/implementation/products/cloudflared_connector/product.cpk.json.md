Source: [products/cloudflared_connector/product.cpk.json](../../../../products/cloudflared_connector/product.cpk.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This descriptor names the owned published cloudflared wrapper for an outbound tunnel connector. It exposes no workload sockets, provider ports, retained mounts or health checks. Its empty secret-delivery list does not mean the connector runs without a credential: the generated tunnel token is supplied through the separate runtime ingress workflow.

The connector is distinct from the local gateway and Cloudflare API interpreter. It owns neither DNS records, gateway target maps nor graph truth. Image provenance records the selected upstream base and command shape; descriptor values and catalogue hashes alone do not verify current tunnel reachability.

Related source and evidence: [products/cloudflared_connector/Dockerfile](../../../../products/cloudflared_connector/Dockerfile), [products/cloudflared_connector/tests/test_cloudflared_connector_product.py](../../../../products/cloudflared_connector/tests/test_cloudflared_connector_product.py), [coordinates/server-products.json](../../../../coordinates/server-products.json).
