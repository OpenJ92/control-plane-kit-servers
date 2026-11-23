Source: [gateway_self_health_diagnostic.py](../../../scripts/gateway_self_health_diagnostic.py).
Maintain this companion with its source and selected contracts.

Thin container entrypoint delegates plan/run to the product-owned diagnostic
composition. It adds no network service or provisioning. Host use is not the owner
validation path. Plan loads only fixed public artifact filenames and the candidate
packet; run additionally requires independently reviewed protected bootstrap and
approval. The [operator guide](../../gateway-self-health-diagnostic.md) links
the maintained client and the historical #221 recipe.
