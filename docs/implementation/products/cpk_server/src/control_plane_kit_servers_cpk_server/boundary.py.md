Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This framework-neutral adapter maps HTTP routes and MCP operation names to one
application service per Core role. Construction requires every role and a
callable verifier; dispatch itself invokes the selected service. Returned
principals travel with path parameters and payload rather than raw credentials.
The transport does not confer workspace authority or admit a desired graph's
node permissions.

HTTP first matches a route, then authenticates, then decodes its payload.
Unknown routes return 404; credential failures return 401 before body/query
decoding. GET rejects a body and bounds raw query bytes by the selected route
schema. It accepts only unique limit and after fields: strict percent/UTF-8
decoding, positive decimal limit syntax and an object cursor with unique JSON
keys, finite numbers and maximum container depth 64. It deliberately leaves
page limits and cursor semantics to Operations; plus is not form-space
decoding here.

Commands reject query arguments and bound body bytes, then accept an empty
body as an empty mapping or a JSON object. This path uses ordinary json.loads;
the read cursor's duplicate-key, finite-number and nesting hardening is not
applied universally to command JSON. Named request schemas here supply the
byte limit, not application-domain validation.

MCP accepts an already decoded mapping. It checks required header presence,
authenticates, compares the method header with the message and resolves either
a parity name or route ID. tools/call cannot select a read-only route and
resources/read cannot select a command. This owner does not validate all
Accept/protocol-version values, impose a serialized MCP input limit or provide
a complete streaming MCP server; the outer host owns its transport admission.

Known CpkServerApplicationError status/message descriptors pass through. At the
selected Operations pin, that error validates status and nonempty text but
does not cap or scrub the message, so producers must supply safe public text.
Other exceptions from service dispatch become a fixed 500. Result conversion
after dispatch, request dataclasses and arbitrary caller-supplied mappings are
not a general redaction/validation membrane. There is no database transaction,
effect execution, history store or response-size enforcement in this owner.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py), [products/cpk_server/tests/test_http_mcp_boundaries.py](../../../../../../products/cpk_server/tests/test_http_mcp_boundaries.py), [pyproject.toml](../../../../../../pyproject.toml).
