Source: [products/cpk_server/tests/test_topology_client_catalogue.py](../../../../../products/cpk_server/tests/test_topology_client_catalogue.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests use local files/journals and scripted public responses to check
saved-draft client composition. Before-mutation callbacks inspect the persisted
invocation, ensuring session and draft intent are recorded before their HTTP
dispatch and the opaque graph reaches the server request unchanged. Selection
keeps the exact revision and initial desired fences without calling deployment
prepare.

Lost-response cases compare exact resumed requests and keep completed receipts
historical, without new reads. Negative cases include fresh closed sessions,
malformed/foreign replies, auth refusal, overflow, changed source files, changed
targets, corrupt journals and crossing catalogue/deployment command modes.
These are client-law witnesses, not a real Operations engine's replay or
transaction proof.

Read tests assert selected/head distinctions, explicit unavailable states,
bounded cursor handling and omission of fixture graph/title/history material.
The read-only path leaves the absent state directory absent. Invalid cursor
JSON/cycles are exercised at CLI, facade and response boundaries. Scripts
supply synthetic status/action data; no live server, provider mutation or fresh
convergence evidence is established.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py), [products/cpk_server/tests/test_topology_client.py](../../../../../products/cpk_server/tests/test_topology_client.py).
