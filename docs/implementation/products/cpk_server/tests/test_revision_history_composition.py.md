Source: [products/cpk_server/tests/test_revision_history_composition.py](../../../../../products/cpk_server/tests/test_revision_history_composition.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests connect the installed preparations/attempts revision-history reads
to HTTP and both existing MCP names. They assert route templates, GET/read role,
page limit ten, scope/cursor transport and principal preservation. Recording
services witness dispatch shape, not stored history results.

Missing or invalid credentials must fail before dispatch. A real adopted
Operations CpkServerReadService plus a UoW factory that raises if opened checks
foreign-workspace denial and malformed revision, limit and scoped cursor
rejection before persistence. Responses have selected bounded-size/redaction
assertions. The accepted workspace principal itself comes from a test verifier.

The suite never opens a database or demonstrates history ordering, pagination
over real rows, transaction behavior or restart retention. Those semantics
remain upstream. Read the consumer's actual Core/Operations pin before updating
route or cursor expectations; local transport success is not a fresh history
claim.

Related source: [composition](../src/control_plane_kit_servers_cpk_server/composition.py.md),
[HTTP/MCP boundary tests](test_http_mcp_boundaries.py.md).
