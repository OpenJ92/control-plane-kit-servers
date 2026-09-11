Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This transport resolves only routes from the pinned Core public HTTP contract,
substitutes percent-encoded path values and selects the profile credential role
for each call. Command JSON disallows NaN and is bounded by the route's request
schema. GET payloads become query fields, with limit encoded as an integer and
other values as JSON; the client does not apply the same total query bound or
all server query semantics before sending.

Requests carry Bearer auth, JSON Accept and the product User-Agent. The opener
refuses redirects and uses a configurable timeout within the admitted range.
There is no automatic retry. A timeout or transport failure after a command
does not prove the server failed to mutate; the workflow/journal owner must
interpret uncertain delivery under the public command contract.

Responses are read up to 1 MiB plus one byte and oversized bodies reject.
401/403 become an authorization error; other HTTP/transport failures become
categorical errors without response bodies. Accepted JSON must be an object
with no duplicate keys; this layer does not validate the operation's result
schema or apply all finite-number/nesting rules. Some decoding failures retain
their original cause.

The finally block clears local credential/header bindings, not every copy:
the Request already holds its Authorization header. This is not zeroization or
universal exception-chain redaction. Profile endpoint policy, standard urllib
TLS/proxy behavior and application-level response checks remain separate
boundaries; no provider API is called directly by this owner.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py), [products/cpk_server/tests/test_topology_client.py](../../../../../../../products/cpk_server/tests/test_topology_client.py), [pyproject.toml](../../../../../../../pyproject.toml).
