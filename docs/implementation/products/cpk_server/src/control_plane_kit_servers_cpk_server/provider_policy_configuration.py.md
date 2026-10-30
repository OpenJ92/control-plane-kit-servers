Source: [provider_policy_configuration.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/provider_policy_configuration.py).

Frozen installer metadata combines the accepted Operations policy with a tuple
of exact binding/client configurations. Duplicate binding IDs are rejected;
full binding equality selects the concrete accepted Interpreter client lazily.
No client or credential is acquired at construction. Enclosing representations
hide installer values. Policy is shared by command/current-read/public owners.

The closed bounded JSON loader rejects unknown/duplicate fields, invalid identities,
missing binding references and invalid endpoint/path metadata. The regular-file
reader uses nofollow/nonblocking open, checks size/type, and caps actual bytes;
parent directories are installer-trusted. Detached fixed errors do not retain
private parser exception context. Referenced credentials are not opened here.

Installer binding IDs must change when retargeting the endpoint/credential identity.
Servers does not invent a durable rebinding detector. Missing exact bindings fail
closed; multiple principals may share a binding. Synthetic composition tests cover
these connections. Source checkpoint awaits the unchanged owning Docker gate.
