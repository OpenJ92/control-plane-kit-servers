Source: [gateway_self_health_diagnostic.py](../../../scripts/gateway_self_health_diagnostic.py).
Maintain this companion with its source and selected contracts.

Thin container entrypoint delegates plan/run to the product-owned diagnostic
composition. It adds no network service or provisioning. Host use is not the owner
validation path. Plan loads only fixed public artifact filenames and the candidate
packet; run additionally requires independently reviewed protected bootstrap and
approval. See docs/gateway-self-health-diagnostic.md for invocation and held effects.

#340 inventories this entrypoint for retirement after exact public replacement
proof. The original invocation recipe is retained in
`docs/learning/gateway-self-health-diagnostic-221.md` as historical evidence;
`docs/gateway-self-health-diagnostic.md` now records pending retirement rather
than a routine operator procedure. Source and tests remain unchanged at this
checkpoint. The product's input/bootstrap readers also serve the retained
`gateway_ingress_admission.py` diagnostic, so whole-family deletion must first
resolve that consumer. See `docs/operational-framework-retirement.md`.
