Source: [products/hello_server/src/control_plane_kit_servers_hello_server/server.py](../../../../../../products/hello_server/src/control_plane_kit_servers_hello_server/server.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

## Ordinary application boundary

This stdlib process serves escaped greeting HTML, liveness/readiness, dependency declarations and a small in-memory request-observation projection. It imports no CPK topology or runtime interpreter. main validates the port/palette before binding 0.0.0.0; environment is runtime configuration, not a control-plane command API. Greeting escaping and a closed palette prevent markup/style injection through those fields.

Dependency declarations admit unique names and environment-name pairs. If either explicit pair member is absent, both conventional names are selected. Parsing constrains shapes/names but sets no aggregate dependency count or JSON-byte quota. Readiness runs the declared checks; liveness is static. HTTP checks disable redirects and read at most the configured cap plus one, but do not classify that extra byte as overflow. PostgreSQL checks only open TCP to the parsed host/port; they do not authenticate or execute a query. Environment-provided dependency addresses have no CPK probe-address-policy admission here.

## Observation and disclosure limits

The handler records successful root GETs in a locked deque retaining twenty method/path records; it does not retain request headers or bodies. The helper strips query material, but this is a selected observation projection, not durable request history or proof every request is represented. Access logs are suppressed. Public dependency descriptors expose environment names rather than their resolved endpoint values.

Network checks have individual timeout arguments, not an independently enforced whole-readiness deadline. Fixed/class-name error text limits ordinary endpoint disclosure, while underlying configuration/parser causes and arbitrary supplied names are not universally sanitized. This small example is not the control-plane auth, durable history or probe-verification owner.

Related source and evidence: [products/hello_server/product.cpk.json](../../../../../../products/hello_server/product.cpk.json), [products/hello_server/tests/test_hello_server_product.py](../../../../../../products/hello_server/tests/test_hello_server_product.py), [products/postgres_server/product.cpk.json](../../../../../../products/postgres_server/product.cpk.json).
