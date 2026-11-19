Source: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This owner implements the signed capability boundary before target I/O.
It decodes at most 4096 body bytes through the pinned Core request codec,
accepts a bounded CPK-Gateway authorization value, selects a configured public
Ed25519 key from the JWT header and verifies the signature. Header and claim
key sets are closed; issuer/audience/time/JTI claims must agree with the decoded
grant. Authority must name this gateway and the canonical workspace audience,
and kind/target/canonical request digest must match.

Core owns request shape, path/reference bounds and maximum 300-second grant
lifetime. The verifier does not query a server session, graph, operation,
request record or key-revocation store. Header kid selects a configured key;
there is no additional equality check here between that kid and grant.key_id.
Key material is copied into a read-only map, limited to sixteen public Ed25519
PEMs; key count does not impose a total PEM/configuration byte limit.

GatewayProbeReplayCache owns the sole clock and skew policy (default five,
supported zero through thirty seconds). After signature/claims/authority/request
checks, remember_once(jti, issued_at=I, expires_at=E) performs one decision under
its lock. It samples t=int(clock()) once. A sample below its last observed second
fails TEMPORALLY_INVALID without changing time history or entries. Otherwise it
records t before applying I<=t+S and t<E+S; even a temporally denied authenticated
candidate contributes its observed time. Such temporal denial does not evict or
insert entries. For a temporally valid candidate it prunes deadlines <=t, rejects
duplicates or full capacity with REPLAYED, then inserts JTI with deadline E+S.
The map remains bounded at 4096 and stores no token material.

The clock sample, high-water update, temporal validation, pruning and replay
admission share the same lock; an earlier verifier timestamp cannot race with
another call's pruning. Clock rollback denies until catch-up. Request mismatch
now precedes temporal mismatch for a doubly invalid request, and invalid
signature/claims/authority/request never samples the cache clock. Cryptographic
work and target effects remain outside the lock. Cache clock/skew are process
configuration, not per-request policy inputs.

A verified JTI is consumed before target lookup/effect; target failure does not
restore it. A new cache/process forgets prior uses, as the existing test shows.
There is no durable replay transaction, automatic retry, distributed cache or
restart protection. The high-water value is local and is not a general clock
correction service.

Errors and repr omit compact token material in their own text; the HTTP owner
projects generic codes. Exception context is not universally suppressed, and
body/JWT JSON decoding does not add duplicate-key rejection. Core/runtime
validation and library failures are not all guaranteed to become the same
GatewayProbeVerificationError. These bounds are not a complete ingress/log/
exception sanitization policy. Source tests do not establish image adoption or
live gateway acceptance.

Related source and evidence: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py), [products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py](../../../../../../products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py), [scripts/cpk_local_gateway_structural_grant_check.py](../../../../../../scripts/cpk_local_gateway_structural_grant_check.py).
