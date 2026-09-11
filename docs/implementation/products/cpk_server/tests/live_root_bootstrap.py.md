Source: [products/cpk_server/tests/live_root_bootstrap.py](../../../../../products/cpk_server/tests/live_root_bootstrap.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This owning witness supports prepare/check/digest/unchanged/cleanup actions for
the real root launcher. Prepare writes a private documented input, generated
fixture material and state under /witness. Check consumes launcher plan/result/
receipt files and reads exact Docker resources; it does not itself substitute
a direct backend deployment for that launcher.

Successful checks require local-ready with external endpoint unverified,
completed authenticated setup, selected image digest/run identity, declared
secret mounts/file observations and CPK-only Docker bind/group configuration.
Selected product log tails must omit fixture material. A process-executed
public client tests wrong-credential denial, and receipt-before captures bytes
for a later unchanged assertion. This does not test an external endpoint,
child deployment, provider mutation authority or a full secret/log scan.

The independent image-account baseline records one reviewed image/config/
passwd/group identity. Expected process groups combine that baseline with the
declared socket GID, never infer expectations from the observed process.
verify_numeric_socket_read requires the exact baseline image, runs without a
user/group override, and checks UID/primary/effective groups plus socket type.
It issues one bounded GET /info and correlates a hash of the returned daemon
ID. Child and controller deadlines, capped wire/output bytes and closed
failure projections distinguish unavailable evidence from a failed law.
A controller timeout does not itself cancel a possibly created remote exec.

Authority diagnostics retain a bounded private record only after engine/
container/image/label correlation, using exclusive no-follow file creation
under a private directory. Observed/configured mounts and groups can remain
explicitly unknown. Public output contains only bounded shape/status/digest
information. This diagnostic cannot replace conformance or numeric socket
evidence, and the baseline cannot be reused for another candidate merely by
changing its image reference.

Cleanup requires a complete, nonpending receipt, matching daemon and run
identity, then checks labels and removes exact recorded IDs in container/
volume/network order with disappearance readback. It holds uncertain acquisition
because effects can lack recorded IDs. Missing receipt returns without cleanup;
it does not prove no resources exist. There is no broad label sweep, pruning or
adoption. Cleanup does not rewrite the receipt and is not generally repeatable
after recorded resources have already been removed.

The source includes effects and destructive cleanup for an explicitly released
owning gate. Its checks and hardcoded reviewed coordinates are apparatus, not
fresh evidence or authorization to retry the separate held grandparent run.

Related source and evidence: [products/cpk_server/tests/live_numeric_bootstrap.py](../../../../../products/cpk_server/tests/live_numeric_bootstrap.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py), [bootstrap.sh](../../../../../bootstrap.sh), [products/cpk_server/tests/test_root_bootstrap_diagnostics.py](../../../../../products/cpk_server/tests/test_root_bootstrap_diagnostics.py), [scripts/cpk_server_image_smoke.sh](../../../../../scripts/cpk_server_image_smoke.sh).
