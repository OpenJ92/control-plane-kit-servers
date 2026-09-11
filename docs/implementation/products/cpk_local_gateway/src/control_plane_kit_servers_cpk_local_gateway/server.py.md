Source: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

The process turns a configured target map into two closed probe effects:
HTTP GET status and Postgres SELECT 1. It owns neither graph truth nor node
creation. Target-map factories allow at most 128 named entries, check protocol,
host/URL and credential-shaped fields, and sort the map. These checks do not
prove graph derivation or private-network membership; URL/host strings and some
text fields have no aggregate size bound. Direct dataclass construction also
bypasses factory checks, and a frozen configuration does not freeze its mapping.

create_app requires a supplied verifier or explicit environment-configured
Ed25519 issuer/audience/node/public keys. POST /cpk/probes buffers the request
body, verifies its signed capability, then encodes the accepted Core request
and dispatches against declared targets. Capability validation precedes target
I/O; an otherwise valid grant for an absent target is still rejected.
The exported execute_probe function itself does not authenticate and accepts a
mapping with fewer constraints than the HTTP/Core codec path.

Live and ready are public constant minimal responses, without target counts or
target probes. They do not prove downstream readiness. main binds uvicorn to
0.0.0.0; deployment owns host exposure. Configuration/verifier startup errors
return exit 2.

HTTP uses the configured base plus an absolute request path, a five-second
opener timeout, disabled redirects and a 16 KiB response read bound. It reports
status/body size without returning response content. urllib HTTP/network
failures are not universally converted into the route's bounded error shape.
Postgres reads a password from the configured environment-name reference, uses
a five-second connection timeout and autocommit SELECT 1, and requires row (1,).
There is no statement deadline or whole-request deadline here.

Verification failures return a generic capability-rejected result with the
verifier's status. Configuration/probe failures return a fixed code and the
exception message; Postgres wraps failures using only their class name in that
message but preserves the cause. The two handled exception categories are not
a universal error/log redaction boundary. The verifier's body limit applies
after inbound.body has buffered bytes; it is not an ingress streaming cap.
These limitations and direct-call trust remain separate from descriptor claims.

Related source and evidence: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py), [products/cpk_local_gateway/product.cpk.json](../../../../../../products/cpk_local_gateway/product.cpk.json), [products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py](../../../../../../products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py), [scripts/cpk_local_gateway_private_probe_smoke.sh](../../../../../../scripts/cpk_local_gateway_private_probe_smoke.sh).
