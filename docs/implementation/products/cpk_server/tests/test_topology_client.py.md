Source: [products/cpk_server/tests/test_topology_client.py](../../../../../products/cpk_server/tests/test_topology_client.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests combine a scripted public transport, deterministic invocation IDs
and temporary files/journals to witness the client's composition. The fake
answers with graph/plan/approval/run receipts; it does not execute Operations
state machines or prove a provider effect.

The public-chain test distinguishes prepare from later mutation, checks route
coordinates and operator/approver/worker selection, uses separate execute keys
for successive progress, and requires exact execution/destructive approval
confirmation. A wrong plan cannot replay a pending approval. Lost preparation
compares exact requests; malformed or unavailable plan evidence returns
attention without advancing to later commands.

Lost execution remains unverified and does not advance current; explicit apply
reads public run/events before replay. Synthetic completion then allows the
fake advancement path. In-flight is reported as running plus attention, while
lost post-execution or post-advance reads retain succeeded execution with
unverified advancement. This is client protocol evidence, not proof that any
uncertain real provider operation can safely be retried.

Status works during the writer lock, refreshes destructive scope and changes
despite altered cached last_result, and rejects a changed target. Journal
cases reject semantic corruption, oversized/malformed records and a foreign
partial-file symlink while preserving that symlink. Assertions that fixture
message and secret-reference strings are absent cover selected graph-body
omission, not a general secret scanner or crash/filesystem-race proof.

One case composes and codec-roundtrips a real installation-shaped graph, then
verifies both declared and removed runtime_authority_deliveries reach prepare
unchanged without runtime-authority commands. It proves permission transport,
not admission or grant. A separate mocked HTTP opener checks product
User-Agent, URL/method and retained Authorization header. Profile/CLI helpers
check private profile loading, symlink/name rejection, entrypoint metadata and
attention JSON/exit 4; no actual endpoint or credential service is contacted.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py), [products/cpk_server/tests/test_docker_installation.py](../../../../../products/cpk_server/tests/test_docker_installation.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py).
