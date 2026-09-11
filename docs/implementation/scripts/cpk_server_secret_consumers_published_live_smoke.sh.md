Source: [scripts/cpk_server_secret_consumers_published_live_smoke.sh](../../../scripts/cpk_server_secret_consumers_published_live_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This opt-in matrix reads six product coordinates with host Python and checks
digest-shaped references plus the configured Docker-in-Docker image. Its parser
requires one matching product entry, not full coordinate consistency.
PLAN_ONLY exits after local selection, before Docker pulls/builds or live runs.

Normal execution pulls those images, builds a source controller, disables
product builds and dispatches ordinary provider, Cloudflare custody and remote
TLS custody launchers sequentially. Pulling a listed image does not establish
that every scenario uses it: descriptor and launcher selection still govern
actual products. This wrapper does not export every selected image as an override.

Credentials, runtime/provider effects, restart evidence and cleanup belong to
the delegated harnesses. There is no rollback trap across the three runs; the
residue audit occurs only after all return success. Coordinate selection and
the final echo are not independent published-image parity or absence evidence.

Related source: [coordinate manifest](../coordinates/server-products.json.md),
[provider launcher](../../../scripts/cpk_server_secret_provider_source_live_smoke.sh),
[Cloudflare launcher](../../../scripts/cpk_server_cloudflare_secret_custody_source_live_smoke.sh),
[remote TLS launcher](../../../scripts/cpk_server_remote_tls_secret_custody_source_live_smoke.sh),
[residue audit](docker_residue_audit.sh.md).
