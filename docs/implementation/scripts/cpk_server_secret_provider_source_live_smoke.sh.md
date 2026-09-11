Source: [scripts/cpk_server_secret_provider_source_live_smoke.sh](../../../scripts/cpk_server_secret_provider_source_live_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This fixture optionally builds controller/CPK/Secrets images, generates provider
master/client keys, password variants and a gateway key, then starts Postgres,
a durable SQLite-backed Secrets process and provider-configured CPK. It dispatches
the ordinary, delegation-bootstrap or verifier-projection controller scenario.
Only verifier-projection requires explicit gateway digest/source coordinates
here; the controller validates their syntax. Selection is not image provenance.

Provider credentials intentionally grant fixture operations across workspaces;
CPK has separate operator, worker and limited-worker static credentials. The
controller receives provider bootstrap files, database URL and Docker socket,
so it is privileged fixture machinery, not a public-only client. Host Python is
used for credential/principal generation. Verifier mode also obtains and stages
GHCR credentials from gh. File chmod0400 does not itself establish the CPK
recipient UID's ownership/access; this shell performs no matching chown step.

Postgres readiness uses local psql and provider readiness checks HTTP200. Actual
secret resolution, rotation/revocation, restart and denial assertions belong to
the Python controller. BUILD_IMAGES=0 suppresses builds but does not independently
require every configured image to be immutable or forbid implicit Docker pulls.

After success the shell scans selected secret-file lines against CPK/provider
logs, an Operations dump and the SQLite database file. This is selected literal
absence evidence, not exhaustive encoding/WAL/encryption or log-redaction proof.
Missing scan files are skipped; command/pipeline errors are not distinguished
from every negative match. Failure prints line-count tails without these scans.

Exit cleanup removes captured infrastructure and scans sixteen fixed workspace
label values across daemon containers/volumes/networks with suppressed failures.
Those labels are not unique run custody and may match another run. It then
deletes the entire state root, including provider data, master material and dump,
even after controller failure. There is no checkpoint-based preservation or
authoritative abort orchestration in this wrapper; the residue audit is a later
success-path check, not an exact cleanup receipt.

Related source: [controller](../../../scripts/cpk_server_secret_provider_source_live.py),
[process composition](../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py.md),
[published gateway wrapper](cpk_server_gateway_published_live_smoke.sh.md),
[residue audit](docker_residue_audit.sh.md).
