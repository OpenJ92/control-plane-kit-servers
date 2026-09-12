Source: [products/cpk_server/tests/test_current_cpk_server_composition.py](../../../../../products/cpk_server/tests/test_current_cpk_server_composition.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite checks current package adoption and server composition through
metadata/text/AST inspection, actual imports, Core route values and selected
service construction. Its independent expected Core/Operations and Interpreters
revisions must match the canonical manifest and generated package/Dockerfile
pins. Servers #177 selects reviewed Core/Operations e3e29995 and Interpreters
e19da40. The constants change with deliberate accepted dependency adoption;
every equality and pin-count assertion remains intact. Counting pins does not
verify registry bytes or execute an image.

Retired names/routes are checked against a named inventory, current Core
language and script text. The test called complete retired inventory means
that specified set, not discovery of every possible obsolete behavior.
A single server service-map call must use current keywords, retain gateway
probe/key registration wiring and omit retired arguments.

Public deployment route presence, HTTP/MCP prepare parity and required
composition keywords are asserted. With DeploymentProgram construction
patched, the real adopted service-map factory must compose
SavedDeploymentPreparationService with the same UoW/operations dependencies.
This is wiring evidence, not a session/admission transaction test.

The saved-draft service test disables schema installation and makes any
database connection fail. Real server construction installs the actual draft
service; malformed create/revise/select commands through HTTP- and MCP-shaped
service requests fail before database use. Assertions check shared UoW/clock/ID
dependencies. The case bypasses network authentication and does not exercise
valid mutation, real PostgreSQL, external effects or a live ASGI listener.
Broader runtime acceptance belongs to the owning gates.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py), [coordinates/server-products.json](../../../../../coordinates/server-products.json), [pyproject.toml](../../../../../pyproject.toml), [products/cpk_server/Dockerfile](../../../../../products/cpk_server/Dockerfile), [products/cpk_local_gateway/Dockerfile](../../../../../products/cpk_local_gateway/Dockerfile).
