Source: [products/cpk_server/tests/test_http_mcp_boundaries.py](../../../../../products/cpk_server/tests/test_http_mcp_boundaries.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite invokes the framework-neutral boundaries using recording services
and a deterministic verifier. It checks HTTP/MCP projection to the same service
requests and principals, route resolution, auth-before-sensitive-decode, body
and query byte boundaries, and categorical rejection before service dispatch.

Paged-read cases preserve an opaque cursor object while leaving semantic page
limits/cursor validity to Operations. Negative cases cover duplicate decoded
fields, malformed escapes/UTF-8, duplicate nested JSON keys, nonfinite numbers
and excessive cursor nesting. These cursor laws are not automatically claims
about command-body JSON or outer HTTP/MCP parsing.

Credential witnesses include absent/invalid/oversized and raw duplicate
headers; a direct verifier-error case checks its exception is not retained.
This does not test every extraction exception chain. The command test whose
name mentions delegation actually verifies missing and unrecognized bearers
both fail; other cases cover successful shared dispatch.

The node-permission case transports a real compiled installation graph both
with and without its declared runtime-authority delivery. Both reach the
recording planning service unchanged. This proves preservation, not permission
admission, graph convergence or provider execution. Known application errors
are tested for status/message propagation, not arbitrary-message sanitization.
There are no sockets, database effects or live deployments in these boundary
calls; the fake verifier intentionally records synthetic credential bytes.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py), [products/cpk_server/law-cards/extract-f-814.json](../../../../../products/cpk_server/law-cards/extract-f-814.json), [products/cpk_server/tests/test_docker_installation.py](../../../../../products/cpk_server/tests/test_docker_installation.py).
