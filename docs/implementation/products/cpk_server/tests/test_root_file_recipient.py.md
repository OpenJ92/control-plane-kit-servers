Source: [products/cpk_server/tests/test_root_file_recipient.py](../../../../../products/cpk_server/tests/test_root_file_recipient.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These two mock-based tests define when numeric image ownership is needed.
An environment-only node with no protected files returns None and never calls
secret_file_owner_uid, even if that method would reject the image USER.

A file recipient delegates once, returns the helper's UID and preserves the
exact rejection exception. This protects conditional ownership validation;
it does not parse image accounts, materialize files, verify mounted ownership
or prove access from a running container.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py).
