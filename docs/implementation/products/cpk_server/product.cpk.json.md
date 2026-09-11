Source: [products/cpk_server/product.cpk.json](../../../../products/cpk_server/product.cpk.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

The base CPK descriptor exposes direct HTTP API and MCP Streamable HTTP
providers on port 8080. Four required Postgres sockets supply workplace,
activity-history, observer-state and graph-topology URLs. The process currently
requires those role URLs to converge on one instance database; the descriptor
itself only describes their communication boundaries.

Its execution-capable process selection disables runtime and ingress
interpreters. CPK_CONTROL_AUTH_CONFIGURED=true is public metadata, not a bearer
credential or proof that a verifier accepted a caller. The only secret delivery
declared here is a Postgres password reference into PGPASSWORD; authentication
and runtime authority require their separate installation/bootstrap inputs.

Compute is ephemeral and this product declares no retained mounts: durable
truth belongs to the connected stores. Live/ready checks and log-readable
capability describe interpreter obligations rather than observed success.
Parents enter the child's public endpoints directly; recursive proxying is
outside this contract. The image is shared with the two interpreter-enabled
variants, whose different identities do not create separate implementations.

Related source and evidence: [products/cpk_server/product.docker.cpk.json](../../../../products/cpk_server/product.docker.cpk.json), [products/cpk_server/product.docker-cloudflare.cpk.json](../../../../products/cpk_server/product.docker-cloudflare.cpk.json), [products/cpk_server/bootstrap.contract.json](../../../../products/cpk_server/bootstrap.contract.json), [products/cpk_server/tests/test_product_descriptor.py](../../../../products/cpk_server/tests/test_product_descriptor.py), [coordinates/server-products.json](../../../../coordinates/server-products.json).
