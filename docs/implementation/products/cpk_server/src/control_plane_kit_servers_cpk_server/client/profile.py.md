Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This owner loads one named private profile from the configured XDG/default
directory and validates its closed schema, endpoint, workspace, three credential
roles and absolute file/state references. It reads profile data immediately;
credential bytes are loaded only when a role is used. The endpoint digest is
SHA256 of its normalized text, not a server identity or workspace digest.

Private-file reads reject currently observed symlink components, open with
O_NOFOLLOW where available, and check the opened file is regular, owned by the
current UID and inaccessible to group/other. They enforce stat and read bounds:
64 KiB for profiles and 16 KiB for credentials. This is not an atomic
directory-descriptor traversal protecting every ancestor against replacement.
A missing/unsafe file fails; loading a profile does not create its state
directory or prove the credential is accepted by the server.

Endpoints normalize host case/trailing slashes, forbid userinfo/query/fragment
and require HTTPS except named loopback HTTP. Literal parent path segments are
rejected, but this is not exhaustive URL canonicalization, DNS pinning or
remote-server authentication. Credentials must be nonempty whitespace-free
ASCII; the client bound exceeds the current server's 4096-byte bearer bound.

Frozen profile fields still contain a caller-supplied mapping rather than a
deep immutable copy, and repr includes endpoint/file references. Fixed error
messages can retain causes such as decoding or OS errors. Keep profiles and
errors private; this owner is not a universal path/credential redactor.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py), [products/cpk_server/tests/test_topology_client.py](../../../../../../../products/cpk_server/tests/test_topology_client.py).
