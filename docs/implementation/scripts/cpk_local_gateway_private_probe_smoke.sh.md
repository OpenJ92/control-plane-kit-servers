Source: [scripts/cpk_local_gateway_private_probe_smoke.sh](../../../scripts/cpk_local_gateway_private_probe_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This legacy shell witness pulls descriptor-selected gateway/Hello/Postgres
images (or overrides), creates a process-named Docker network and three
containers, publishes only the gateway to a loopback host port, and attempts
HTTP/Postgres probes plus missing-target/unsupported-kind rejection.
It is direct Docker/curl apparatus, not a public control-plane execution path.

The current script supplies neither required Ed25519 verifier environment nor
signed probe Authorization headers. Its unsigned requests also predate the
canonical request codec's complete shape. It therefore does not establish
acceptance of the maintained authenticated gateway source. An image override
or historical descriptor selection is not proof of current-source parity.

It uses host Python for descriptor lookup, port selection and result checks,
fixture database credentials and fixed /tmp health/error files. The free-port
lookup has a bind/release race. Readiness loops are finite, but curl and the
whole script have no explicit total deadline. Failure may emit Docker logs.

Cleanup targets captured container IDs and the generated network name, suppresses
errors, and does not verify resource disappearance. It does not request volume
removal for image-created anonymous volumes. Container IDs are retained only
after successful command substitution; interrupted creation can leave uncertain
ownership. The final success text is not a durable cleanup or history record.
No broad prune occurs, but this script requires its own governed execution and
cleanup review before use.

Related source and evidence: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py](../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py), [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py](../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py), [products/cpk_local_gateway/product.cpk.json](../../../products/cpk_local_gateway/product.cpk.json), [products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py](../../../products/cpk_local_gateway/tests/test_cpk_local_gateway_product.py).
