Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This private invocation store records locators, target digest/workspace,
desired-source identity, phase, pending request, returned coordinates, bounded
request history and the last projected result. It accepts canonical UUID4
operation references and three schema families; catalogue journals delegate
validation to catalogue.py. These local facts are transport provenance, not
the server's durable graph, approval or execution truth.

Reads initialize the private invocations directory, then open an owner-only
0600 regular file without following the final symlink where supported. They
bound bytes to 1 MiB, compare inode/size/mtime around reading and reject
duplicate JSON keys before schema/phase checks. Existing observed symlink
components reject; this is not an atomic traversal of all ancestors.

A nonblocking advisory flock serializes cooperating mutation callers for an
operation. create/write do not acquire that lock themselves. Creation writes
and fsyncs an exclusively created 0600 partial, hard-links it to a previously
absent final name and fsyncs the directory. Replacement checks the existing
file identity, writes a new partial, rechecks before os.replace and fsyncs the
directory. This protects ordinary cooperating use, not arbitrary concurrent
path replacement between every filesystem call.

Partial cleanup removes only a regular file with the recorded device/inode;
a preexisting or replaced partial is preserved. A crash can leave such a
partial requiring inspection. Failure after publication but during directory
fsync may leave changed durable bytes despite an error; there is no rollback
of a completed link/rename or atomic transaction with an HTTP command.

Validation checks closed phase/coordinate and role/route relationships, result
shapes and a maximum 128 request records. Saved preparation must retain its
exact request; file preparation keeps a file locator/hash instead of embedding
the desired graph. General replay-body hashing and re-reading that file belong
to workflow._replay_pending; not every hash is recomputed here. Stored response
mappings and local file references remain private, and schema checks are not
a universal secret scrubber. There is no automatic journal deletion, provider
cleanup, reauthorization or permission to retry an uncertain mutation.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py), [products/cpk_server/tests/test_topology_client.py](../../../../../../../products/cpk_server/tests/test_topology_client.py), [products/cpk_server/tests/test_topology_client_saved.py](../../../../../../../products/cpk_server/tests/test_topology_client_saved.py).
