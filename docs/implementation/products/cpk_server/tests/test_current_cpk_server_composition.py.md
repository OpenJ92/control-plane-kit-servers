Source: [products/cpk_server/tests/test_current_cpk_server_composition.py](../../../../../products/cpk_server/tests/test_current_cpk_server_composition.py).

## Current receiving adoption (#237)

The receiving candidate selects Core and Operations
250d65e19dc748ebe840f705be77eb732dab3cb3, SDK
5dc93b92c27bb9bbe2af027f945a347e5e4131bc and Secrets
edfb8c0ebfc0cfcf3a667fb60d52b4a83bda1634. Its Interpreters runtime dependency is
accepted Interpreters I-M
bdbab01c0babaead958450b3c5e643317b2f4cd9, whose merge tree equals reviewed
I-C 6137017. Its shipped implementation is byte-identical to producer I-A.
The approved finite paired-gate exception retains S-B 9921911 as the final
Interpreters test witness. Earlier coordinates below are historical. This S-D
adoption still requires the unchanged whole Servers gate before merge.

The existing coordinate generator ran in repository policy Docker image
python:3.14-slim with network disabled and only this checkout writable. Canonical
upstream fields generate pyproject and six product recipes; published source/image
coordinates, product descriptors and both catalogue byte sets are unchanged.
Generation is not test green or image qualification. All existing gate stages,
installed provenance checks, source/historical witnesses and cleanup remain.

Historical context follows; the current adoption above governs selected dependencies.

The September 26 #181 adoption updates exact selected dependencies to Core/Operations f1e6cf2, Interpreters4bb9d857, SDK22f1267b and Secrets43b742d1. Installed provenance and published-image boundaries remain unchanged.
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite checks current package adoption and server composition through
metadata/text/AST inspection, actual imports, Core route values and selected
service construction. Its independent expected Core/Operations and Interpreters
revisions must match the canonical manifest and generated package/Dockerfile
pins. Servers #193 historically selected reviewed Core/Operations95452249 and Interpreters
77c9a7f. The constants change with deliberate accepted dependency adoption;
the current adoption counts complete package archive URLs/subdirectories rather
than bare SHAs: Core and Operations can share a commit while requiring one
distinct URL each. Gateway still must contain one Core URL and no Operations
package dependency. Counting pins does not
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

#221 advances only the independent expected Interpreter coordinate to accepted
388282, matching the canonical diagnostic adoption. Existing assertions remain;
this is installation/composition evidence, not publication or live readiness.
