Source: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This owner implements the signed capability boundary before target I/O.
It decodes at most 4096 body bytes through the actual pinned Core request codec,
accepts a bounded CPK-Gateway authorization value, selects a configured public
Ed25519 key from the JWT header and verifies the signature. The header and
claim key sets are closed; issuer/audience/time/JTI claims must agree with the
decoded grant. Grant authority must name this gateway and the canonical
workspace audience, and kind/target/canonical request digest must match.

Core owns request shape, path/reference bounds and the maximum 300-second grant
lifetime. This verifier applies its clock and configured skew (default five,
maximum thirty seconds). It does not query a server session, graph, operation,
request record or key-revocation store. Header kid selects a configured key;
there is no additional equality check here between that kid and grant.key_id.
Key material is copied into a read-only map, limited to sixteen public Ed25519
PEMs; key count does not impose a total PEM/configuration byte limit.

Replay protection is a lock-protected in-memory JTI map, bounded at 4096.
It rejects retained duplicates and a full map, pruning entries at nominal
expires_at. The verifier can accept a grant within expiry skew after that
nominal time, so this cache does not establish replay exclusion throughout the
skew grace interval. A new cache/process forgets prior uses, as the test
explicitly demonstrates. Verifier and cache clocks are separately supplied.

A verified JTI is consumed before target lookup/effect; target failure does not
restore it. There is no durable replay transaction, automatic retry or shared
multi-process cache. Same-process concurrency before expiry has a dedicated
one-acceptance witness.

Errors and repr omit compact token material in their own text; the HTTP owner
projects generic codes. Exception context is not universally suppressed, and
body/JWT JSON decoding does not add duplicate-key rejection. Core/runtime
validation and library failures are not all guaranteed to become the same
GatewayProbeVerificationError. The header/body limits and bounded error text
do not imply a complete ingress/log/exception sanitization policy.

Related source and evidence: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py), [products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py](../../../../../../products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py), [scripts/cpk_local_gateway_structural_grant_check.py](../../../../../../scripts/cpk_local_gateway_structural_grant_check.py), [pyproject.toml](../../../../../../pyproject.toml).
