# Child-acceptance companion adoption draft

This slice documents the actual unmerged Servers child source at80c3ffd34b157940ec72cfc22156a27dcaa1fc5c. Its baseline readiness source is4e34e74bd45ee60f308323755233ca8f4d800243. [Servers #173](https://github.com/OpenJ92/control-plane-kit-servers/issues/173) owns this adoption draft; [#172](https://github.com/OpenJ92/control-plane-kit-servers/issues/172) owns stable readiness coverage. This draft neither changes the held source branch nor claims these files are adopted on readiness/main.

Follow [#1799](https://github.com/OpenJ92/control-plane-kit/issues/1799): source/update reminder in every companion, verified source and selected imported contracts, proportional review and same-change maintenance. [Inventory](inventory.json) records only the child-added/changed/deleted slice, including overlap that must be refreshed when source adopts. It is not the full readiness inventory and must not replace it wholesale.

At adoption, retarget the draft to the actual accepting branch, review changed bootstrap/runtime/gate/test notes against that source, remove the deleted image-reference-test companion if stable coverage has created it, and merge inventory entries with the stable inventory. No documentation merge into the held child branch is intended. Its existing runtime failure remains held and uncertain.

The calibration links [public child admissions](products/cpk_server/tests/live_child_api.py.md), [child installation preparation](products/cpk_server/src/control_plane_kit_servers_cpk_server/client/installation.py.md), and [gateway evidence tests](products/cpk_server/tests/test_child_gateway_example.py.md). The key distinction is local composition/public import/plan/effect/read evidence; none implies the next stage succeeded.
