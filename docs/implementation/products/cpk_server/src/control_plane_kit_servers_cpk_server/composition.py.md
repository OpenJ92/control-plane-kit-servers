Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This owner builds process-local composition values over the selected Core
handoff language: one deployment program with a service binding for each role,
HTTP read/command routes, MCP, projection/command/security parity and declared
unit-of-work boundaries. Execution declares read/write ownership with effects
after commit, worker use and runtime authority. The READS service declares
read-only store participation; the AUTHORIZATION service declares no store
participation. Neither statement removes request authentication. These are contracts, not running stores,
transactions, workers or proof that an implementation followed them.

Configuration validates boolean flags, known mode names and authentication
when execution is enabled. The factories provide conventional execution-capable
and local-read-only values. The canonical handoff still contains both read and
command routes regardless of that local flag; this value alone is not a
route-filtering or authorization mechanism. The hosted server has its own
stricter bootstrap mode admission.

Process state returns replacement values for observer updates, target changes
and active-target switches. Removing an active target clears the selection;
switching to an unknown target rejects. None of these values own durable graph
truth or move a provider resource. Observer.from_mapping stringifies accepted
scalar fields and limits each value's text to 256 characters, but does not cap
observer/item counts or all identifier lengths; direct ObserverState
construction has no corresponding factory validation.

The composition descriptor emits configuration/handoff/policy rather than
serializing the process target/observer contents. Read current tests and the
historical law cards together: their identity/replay language names the shared
application contract, not a replay ledger implemented in this module.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py), [products/cpk_server/tests/test_process_composition.py](../../../../../../products/cpk_server/tests/test_process_composition.py), [products/cpk_server/law-cards/extract-f-813.json](../../../../../../products/cpk_server/law-cards/extract-f-813.json), [pyproject.toml](../../../../../../pyproject.toml).
