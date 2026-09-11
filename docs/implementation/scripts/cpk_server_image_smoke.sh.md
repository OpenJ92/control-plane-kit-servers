Source: [scripts/cpk_server_image_smoke.sh](../../../scripts/cpk_server_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This image/process witness optionally builds CPK, requires missing-config failure
and image USER 10001, starts Postgres and a loopback-published CPK process, then
exercises authenticated public setup and HTTP/MCP reads. Postgres readiness uses
an authenticated TCP SELECT 1. Runtime interpreters default to none; this is not
a deployment-effect or Docker-socket authority test.

The liveness path validates one loopback port binding, gives host curl explicit
connect/total timeouts and classifies exited/unavailable/invalid container state.
After retries, one internal /health/live probe distinguishes host reachability
from internal liveness using a bounded exact response. The selected host-error
excerpt is capped and flattened. Other curl paths do not share those explicit
timeouts; the script has no universal deadline or response-byte bound.

Most setup checks use grep/sed over compact JSON rather than strict decoding.
Readiness means the returned configured-store projection, not a fresh query of
every dependency. Its selected postgres:// leak check is not universal DSN or
secret redaction. The malformed authenticated MCP command is expected to return
an error; that is not successful activity planning.

The embedded revision-history witness creates a draft through the public server
and asserts exact empty preparation/attempt pages, HTTP/MCP parity, authentication,
cursor/limit rejection and missing-revision errors. Its requests have a ten-second
timeout and 64 KiB response cap. This proves the intended empty-history composition
when executed successfully, not nonempty ordering, execution history or restart.
The actual adopted Core/Operations contracts govern those payloads.

Database endpoint overrides can target caller-supplied durable stores: fixed
workspace, import, session and draft writes are not inherently ephemeral merely
because local Postgres is also started. Cleanup removes captured containers and
a process-named network with suppressed Docker errors, plus temporary files.
It does not roll back public database writes or explicitly delete anonymous
volumes. Capture gaps and verified absence are not closed by a final echo.
Failure tails are line-count bounded, not universally byte-bounded or redacted.

Related source: [server composition](../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py.md),
[image/bootstrap tests](../../../products/cpk_server/tests/test_image_bootstrap.py),
[history composition tests](../products/cpk_server/tests/test_revision_history_composition.py.md),
[residue audit](docker_residue_audit.sh.md).
