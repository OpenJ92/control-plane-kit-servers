Source: [health_receiver_adapters.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/health_receiver_adapters.py).

This CPK composition module implements the public Operations receiver port using existing product-owned parsers. Explicit exact canonical documents produce immutable bindings for the fixed workload or gateway profile/slot. The caller still owns supported-product/input admission: accepting a supplied document is not catalogue discovery or an image support claim. Empty input retains Operations' fail-closed registry.

Each decoder revalidates HealthReceiverSelection provenance and selected artifact, enforces its bound reference/slot and decodes only those bytes. Workload facts come from health issuer/keys, target/runtime/declaration; static surface authority is not substituted. Gateway facts come from configured workspace/gateway/runtime/issuer/purpose/keys. Operations compares these facts to its independently pinned expected context. Descriptor default bytes are never trust fallback.

Only the explicit product parsing refusals become the fixed HealthReceiverTrustError outside caught exception context. Unexpected decoder failures propagate. There is no file/network/database access, clock, material resolution, signing, mutable key cache, authority decision or durable history. The public registry does not change first-start/reload invocation; actual production composition and usable lifecycle remain181/1860.

Tests use the real product verifiers and pinned Operations coverage function. Private Operations imports are confined to tests; neither gateway receiver nor SDK acquires an Operations dependency. Full CPK contracts still contain legacy verification; synthetic receiver-only plans do not prove production readiness or deployment.

#219 adds explicit `gateway_self_documents` to the existing registry. A
`GatewaySelfHealthReceiverDecoder` binds the selected `gateway-control`
JSON/read-only artifact and decodes it with the actual #182 codec. Selected
workspace, authored revision, node, runtime and socket must match configured
truth, and the canonical descriptor must declare that exact own READINESS
surface. Existing WorkloadHealthReceiverTrust carries only health issuer/keys;
complete surface-read trust is validated but grants no extra health authority.
Transit and self-health bindings coexist as distinct purposes for one product
reference. Existing defaults and decoders are unchanged.

`select_gateway_self_health_binding(transit=..., targets=..., control=...)`
revalidates three existing HealthReceiverSelection values and their unique
declared slots. Workspace, revision, projection, graph side, receiver, runtime
and canonical product provenance must agree. Transit and target selections use
the declared transit socket; own readiness uses its declared control surface.
Socket names may coincide. Real product codecs parse selected bytes; existing
receiver/control matching functions validate joins. Exactly one binding must
match the full own target, runtime and V2 declaration. Its actual configured alias
is returned without naming inference or default-content substitution.

GatewayHealthTargetBinding includes a private origin and is internal material,
not a route/receipt/history result. This adapter neither logs nor serializes it,
and makes no general repr-redaction promise about that type. Explicit product
codec failures become bounded detached trust errors; unexpected owner failures
preserve identity. No I/O, credentials, signing, attempts, signer admission,
installed-state evidence or async execution is introduced. #148/#1860 consume
selection later; #181 still owns concrete composition.
