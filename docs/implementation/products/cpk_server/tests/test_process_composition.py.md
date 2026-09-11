Source: [products/cpk_server/tests/test_process_composition.py](../../../../../products/cpk_server/tests/test_process_composition.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests check historical law-card ownership, the selected Core handoff's
single program boundary, required authentication for execution and immutable
process-state transitions. Replacing targets must clear a stale active target;
unknown switches fail. They do not give process state durable graph ownership.

Selected catalogue/Core import checks assert product process modules remain
absent in the test process. The Hello assertion checks an unavailable module
name; it is not a general proof that every Hello value fails every CPK law.
Those checks supplement the separate cold-subprocess descriptor tests.

A larger AST assertion inspects server._operations_application wiring:
execution and observation adapters are distinct, share the intended provider
composition, and start/reconciliation share the fold service with distinct ID
factory expressions. This inspects source shape without calling those runtime
services. It proves neither actual concurrent effect folding, transaction
behavior, provider identity nor successful recovery.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py), [products/cpk_server/law-cards/extract-f-813.json](../../../../../products/cpk_server/law-cards/extract-f-813.json), [products/cpk_server/tests/test_product_descriptor.py](../../../../../products/cpk_server/tests/test_product_descriptor.py).
