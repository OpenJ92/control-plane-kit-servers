Source: [bootstrap.sh](../../bootstrap.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This host shell entrypoint runs plan/apply/inspect through an explicit existing
local driver image ID. It inspects that exact ID and never pulls or selects a
mutable driver tag. The script invokes Docker and host path/identity utilities,
not host Python or Compose.

Plan runs a read-only, network-none, capability-dropped container as the caller
UID/GID with only the input file mounted. Apply and inspect require a local
Unix Docker context and reject TLS configuration. The mounted socket is still
/var/run/docker.sock; apply passes the selected daemon ID for runtime comparison
rather than assuming any Unix context names the mounted daemon.

Apply mounts the plan/material read-only and private state read-write, granting
the driver Docker socket access. Inspect mounts private state read-only with
that same socket. Unlike plan, these driver invocations do not set the caller
user or drop all capabilities; acquisition requires the explicit root helper
image. Network-none on the driver does not remove daemon/provider powers.

The wrapper creates the state directory under umask 077 but does not make an
existing directory private. Runtime validation owns that refusal. exec and
--rm do not constitute cleanup of daemon-created acquisition resources, and
the wrapper has no general timeout, retry, adoption or compensation path.
Successful planning is only a reviewable artifact; apply needs its explicit
digest/material/state inputs and the governing operational authorization.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py](../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py](../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py](../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py), [products/cpk_server/tests/test_root_bootstrap.py](../../products/cpk_server/tests/test_root_bootstrap.py).
