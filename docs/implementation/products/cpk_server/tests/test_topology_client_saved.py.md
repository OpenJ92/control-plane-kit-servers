Source: [products/cpk_server/tests/test_topology_client_saved.py](../../../../../products/cpk_server/tests/test_topology_client_saved.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite specializes the scripted transport from test_topology_client for
saved desired revisions. It witnesses client-owned request, journal and restart
laws; it does not recreate the backend's session/admission state machine.

Fresh plan sends exactly draft/revision, original current/desired fences,
generation, title and key under the operator role. The saved journal retains
that request and coordinates without a desired graph body. After a lost
response, a new TopologyClient over the same state replays the exact original
request even when the fake workspace generation changes; the fake forbids a
new workspace read. Once preparation is complete, resume_prepare rejects a
second replay. A separate fresh invocation reads new fences and uses a new
invocation/key, with no draft-select mutation.

Foreign workspace and mismatched submitted graph/projection/generation fields
in plan detail return attention before approval reads. The destructive apply
case rejects an ordinary approval flag before any decision, then accepts the
exact destructive flag and preserves result-v1 plus saved journal provenance.
Convergence comes from scripted public replies, not a live provider witness.

Closed-journal tests reject extra or inconsistent saved-request fields,
boolean/invalid revisions and zero desired generation, and reject catalogue
resume for a deployment invocation without HTTP. Value and CLI cases reject
out-of-bound IDs/revisions and incomplete, mixed or noncanonical input modes
before profile loading or client construction. These cases protect the saved
client boundary; server idempotency, durable transaction and provider restart
correctness remain outside this suite.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py), [products/cpk_server/tests/test_topology_client.py](../../../../../products/cpk_server/tests/test_topology_client.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py).
