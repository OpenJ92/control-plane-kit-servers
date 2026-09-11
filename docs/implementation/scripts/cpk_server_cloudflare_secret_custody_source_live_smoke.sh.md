Source: [scripts/cpk_server_cloudflare_secret_custody_source_live_smoke.sh](../../../scripts/cpk_server_cloudflare_secret_custody_source_live_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This Cloudflare custody fixture chooses timestamp/PID workspace, hostname and
network coordinates, sources the configured authority file as shell code, copies
the API token to private staging and unsets inherited token/tunnel variables.
It generates provider/gateway material, stages GHCR authority, optionally builds
images and launches Postgres, Secrets and provider-backed Cloudflare-enabled CPK.
The controller holds Docker, database and provider access and a writable
checkpoint/inventory directory. These are real effect capabilities.

Static provider grants span the fixture's selected secret intents; CPK grants
use the generated workspace. chmod0400 bounds file modes but does not assign
the provider-client file to the CPK recipient UID. Readiness checks local psql
and HTTP200. Builds-off is not immutable-image or no-pull verification.

The shell snapshots host container IDs/names, network IDs/names and volume names
before fixture networking and compares the sorted inventory after cleanup.
This detects selected inventory differences, not changed contents/labels/data,
and concurrent unrelated changes can also cause a mismatch. Cloudflare inventory
and ephemeral lifecycle evidence are owned by the Python controller.

On controller failure, a present checkpoint enables one abort-cleanup invocation
while CPK/provider/database remain alive. The primary shell status remains
failure. Crucially, a failed abort still proceeds to local fixture teardown and
deletion of STATE_ROOT, including checkpoint, provider database/master material
and diagnostics. This is not a preserve-on-uncertainty recovery boundary.

Local cleanup uses captured infrastructure IDs plus the generated workspace label,
suppresses Docker failures and compares host inventory. It is more specific than
the ordinary fixture's fixed workspace set, but not a complete exact-resource
or provider-absence receipt. Successful scans check selected secret-file lines
against logs, an Operations dump and SQLite bytes; they do not cover all encodings,
WAL state or arbitrary secret material. Failure prints selected container state,
while the controller owns other diagnostic output and its bounds.

Related source: [controller](../../../scripts/cpk_server_secret_provider_source_live.py),
[abort helper](cpk_server_source_live_abort.py.md),
[lifecycle tests](../products/cpk_server/tests/test_ephemeral_source_live_lifecycle.py.md),
[residue audit](docker_residue_audit.sh.md).
