Source: [scripts/cpk_server_recursive_activity_smoke.sh](../../../scripts/cpk_server_recursive_activity_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This legacy launcher uses host Python to select a parent image and recursively
assemble secret-value JSON, optionally builds a controller, pulls the parent
and starts Postgres/CPK plus a socket-mounted controller. Registry authority may
come from gh or a local Docker configuration and is copied into temporary files
and nested process environments. Static fixture passwords and local-development
resolution are not durable provider custody.

The parent receives CPK_CONTROL_AUTH_CONFIGURED=true without an actual verifier;
current main rejects that configuration. The credential-present branch also
sets rejected legacy Docker-config fields, and child material retains those
settings. Earlier cleanup/build/container effects can precede rejection. This
is a source-derived compatibility limit, not a result from running old images.

Cleanup runs both before provisioning and on exit. It scans daemon-wide workspace
labels matching recursive-cpk-server or the local-chain prefix, including
containers, volumes and networks, with suppressed failures. Matching resources
from another run can therefore be selected. Captured parent/Postgres IDs and
the process-named infrastructure network are also removed; there is no exact-run
absence ledger or preservation-on-uncertainty gate.

The parent database probe is local psql rather than explicit password-authenticated
TCP. Failure prints a line-count log tail without general redaction; success
delegates a residue audit. The script has no independent opt-in or universal
deadline. Its checks and final echo do not prove current recursive readiness.

Related source: [controller](cpk_server_recursive_activity.py.md),
[process admission](../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py.md),
[residue audit](docker_residue_audit.sh.md).
