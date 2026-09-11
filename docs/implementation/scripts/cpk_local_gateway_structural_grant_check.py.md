Source: [scripts/cpk_local_gateway_structural_grant_check.py](../../../scripts/cpk_local_gateway_structural_grant_check.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This synthetic structural check generates an ephemeral Ed25519 key, constructs
one exact HTTP probe and signed grant, and verifies that the gateway/Core
values agree. The workspace/issuer identifiers resemble an earlier source-live
case, while time and identities are fixed fixtures. It does not load actual
credentials or recreate that earlier authority.

The local verifier and replay cache share the fixed clock. Verification must
return the exact request before the script prints success; it does not call
execute_probe or reach a target. The generated private PEM and token remain
process values and are not printed by this helper. It tests one positive
representation/signature path, with no provider, HTTP, replay-negative,
revocation or durable-history claim. The wrapper determines which image runs
it; the script alone does not prove immutable image identity.

Related source and evidence: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py](../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py), [products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py](../../../products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py), [scripts/cpk_local_gateway_structural_grant_image_smoke.sh](../../../scripts/cpk_local_gateway_structural_grant_image_smoke.sh).
