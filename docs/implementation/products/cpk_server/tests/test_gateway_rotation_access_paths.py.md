Source: [products/cpk_server/tests/test_gateway_rotation_access_paths.py](../../../../../products/cpk_server/tests/test_gateway_rotation_access_paths.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This test preserves two closed access-path values across the hosted HTTP and
MCP facade: named-public-ingress and runtime-private. Captured payloads and
scripted responses must carry the enum values.

Despite the historical rotation filename, it neither performs key rotation nor
executes a gateway request. It does not prove a network path was used, a grant
was admitted, or caller-supplied actor fields establish authority. Protocol
admission and provider behavior remain with their actual owners.

Related source: [hosted methods](../../../../../scripts/cpk_server_hosted_activity.py).
