Source: [scripts/cpk_local_gateway_structural_grant_check.py](../../../scripts/cpk_local_gateway_structural_grant_check.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This synthetic structural check generates an ephemeral Ed25519 key, constructs
one exact HTTP probe and signed grant, and verifies that gateway/Core values
agree. Workspace/issuer identifiers resemble an earlier source-live case, while
time and identities are fixed fixtures. It loads no actual credentials and
does not recreate earlier authority.

The replay cache owns the fixed clock used for temporal and replay admission.
The verifier has no second clock argument. Verification must return the exact
request before success is printed; it does not call execute_probe or reach a
target. Generated private PEM and token remain unprinted process values. This
checks one positive representation/signature path, with no provider, HTTP,
replay-negative, revocation or durable-history claim. The wrapper chooses which
image runs it; the script alone does not prove immutable image identity.

Related source and evidence: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py](../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py), [products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py](../../../products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py), [scripts/cpk_local_gateway_structural_grant_image_smoke.sh](../../../scripts/cpk_local_gateway_structural_grant_image_smoke.sh).
