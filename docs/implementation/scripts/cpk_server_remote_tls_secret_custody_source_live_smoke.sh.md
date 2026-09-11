Source: [scripts/cpk_server_remote_tls_secret_custody_source_live_smoke.sh](../../../scripts/cpk_server_remote_tls_secret_custody_source_live_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

The host shell provisions privileged DinD, local Postgres and durable Secrets,
stages generated TLS/provider material plus GHCR credentials, then starts CPK
and the controller without a host Docker socket. CPK receives only provider
bootstrap authority; TLS/OCI values are resolved through admitted references.
Host Python, Docker, direct SQL/audit queries and provider access remain privileged
fixture powers. File mode0400 alone does not establish CPK recipient ownership.

Deploy must create labelled nested containers/networks with the expected configured
Hello image reference. The shell recreates CPK and Secrets over retained stores,
then resumes update/teardown. Selected host workspace inventory must stay equal,
nested labelled resources must disappear and a named TLS temp-directory pattern
must be absent. These checks do not prove remote Hello health: the controller's
product disables semantic verification. Config.Image equality is not a manifest
or executable-byte attestation.

Four denial cases are prepared before full host/remote container, network, volume
and image inventory snapshots. Execute then must leave those snapshots unchanged.
The unavailable-provider case stops/restarts Secrets around execution. Snapshot
equality misses transient create/delete cycles and changes within existing
resources; unrelated concurrent changes can also fail it. It does not prove
that no daemon request was issued.

Direct Operations and provider queries require selected authorization/correlation/
intent/version relationships: denied cases select no version, successful selected
versions map to Operations authorizations, and deploy/update/teardown span at
least three resolved runs. This is a fixture query against actual schema owners,
not an alternate durable semantics layer or exhaustive history audit.

Log/dump/SQLite scans cover selected literal TLS/client/OCI file lines, not every
encoding, WAL state or possible secret. Log capture errors are suppressed and
failure tails may precede scans. Build suppression is not immutable-image or
no-pull enforcement; the DinD image is explicitly pulled.

The exit trap removes captured infrastructure and generated-workspace-labelled
resources with suppressed errors, then deletes all state, provider/master material,
logs and denial evidence even on failure. It does not preserve uncertain-run
evidence or explicitly remove every anonymous DinD volume. The later residue
audit and success echo are not an exact cleanup receipt or authorization to
execute a held scenario.

Related source: [controller](cpk_server_remote_tls_secret_custody_source_live.py.md),
[fixture assertions](../../../products/cpk_server/tests/test_image_bootstrap.py),
[residue audit](docker_residue_audit.sh.md).
