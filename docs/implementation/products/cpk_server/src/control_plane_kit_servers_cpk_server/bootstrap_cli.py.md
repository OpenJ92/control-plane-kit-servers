Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

The CLI dispatches bounded plan/apply/inspect input to the bootstrap owners.
Successful results are canonical JSON on stdout; caught Exception failures
become the closed hold projection on stderr with exit 1, never an SDK traceback
or raw error body. Argument-parser failures and BaseException interruption
remain separate. Reading plan/input here is not the runtime's private-material
file admission.

public_setup runs inside the prepared helper sharing the CPK container network,
with a private setup credential and fixed local endpoint. It re-verifies the
plan and sends existing public routes under the operator role. It polls only
TCP reachability, then sends each planned mutation once; no command retry,
replacement session or plan execution is hidden in setup.

A private progress directory contains a bounded 64 KiB checkpoint. Each command
marks pending before dispatch and records selected returned coordinates before
later validation/commands. Writes use exclusive temporary creation, fsync,
replace and directory fsync; this is not a transaction with HTTP. An existing
progress directory prevents a fresh helper run from silently overwriting it.

The sequence creates a new workspace, registers the provider/reference and
runtime authority/delivery, imports selected products, and registers optional
pull/ingress authorities. Plan-derived deterministic keys and route-order
checks constrain dispatch. Readback checks differ by route; coordinate receipts
are not universal payload validation. Ingress binds its generated provider ID
to the actual registration and compares the public projection's redacted
reference fields with the command result.

Final reads compare initial workspace/current/desired graph coordinates.
Complete means authenticated local setup; external_endpoint stays unverified.
No topology deployment, external DNS/probe, restart acceptance or cleanup is
proved here. The runtime owner recovers bounded progress from the exact helper
and controls its removal. Setup credential/profile paths and progress records
remain private operational material even when raw credentials are omitted.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py), [products/cpk_server/tests/test_root_bootstrap_diagnostics.py](../../../../../../products/cpk_server/tests/test_root_bootstrap_diagnostics.py).
