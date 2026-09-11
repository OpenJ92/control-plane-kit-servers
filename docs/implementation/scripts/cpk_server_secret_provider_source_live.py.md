Source: [scripts/cpk_server_secret_provider_source_live.py](../../../scripts/cpk_server_secret_provider_source_live.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This source-live controller combines public CPK workflows with privileged fixture
operations: provider secret writes/rotation/revocation, Docker restart/inspection,
provider SQLite inspection through container exec, Operations PostgreSQL reads,
gateway probes and optional Cloudflare ingress/abort work. It is acceptance
apparatus, not a reusable authorization or persistence service. Its mode and
scenario selectors choose different effectful paths; importing or documenting
them does not authorize execution. HostedWorkflow supplies automatic fixture
approval, frozen claim generations, fenced advancement and shared transport.

The ordinary scenario registers provider/reference metadata separately from
writing secret material, restarts provider/CPK, deploys version A, rotates to B,
checks old-correlation pinning and a later deployment's version, then tears down
compute. Further scenarios cover revoked-before-use, concurrent workspaces,
resolve/revoke races and denied scope/workspace/intent/provider/reference cases.
Denied execution is capped at 40 one-effect calls and stops on closed terminal
results. A stopped/uncertain result is not by itself proof of authorization
denial. Audit-count and selected Docker inventory checks are witnesses with
limited coverage; the wrong-credential case does not require a new audit row.
Before/after inventories cannot exclude transient or unrecorded effects.

Gateway bootstrap admits a provider-backed signing reference and public key,
restarts processes, replays admission and checks stable registration identity.
The verifier-projection scenario deploys key A and runs private HTTP/Postgres
probes plus adversarial calls, then returns. Rotation-named helpers/files do not
mean that this path executes a complete key rotation. Its Postgres graph empties
verification without changing product identity. Direct denial checks accept a
bounded family of rejection statuses, compare Hello observations and calibrate a
Postgres transaction-count witness. These establish selected observations, not
every possible target request or replay behavior around expiry/restart.

The Cloudflare custody path admits provider, pull, ingress and delegation
metadata, then drives public-on/off/on-again/final EMPTY transitions. It records
optional phase checkpoints before fault injection, tests signed public/private
probes, selected stable workload identities, ingress epochs, generated-token
revocations and provider/Operations correlations. The shared graph builders use
the actual consumer Core 087 contracts. Checkpoints describe completed graph
phases; they are not a transactional journal of every external effect.

Abort first reads checkpoint/workspace identity and exact recorded ingress
resources. It separates accepted successful graph evidence, reconstructable
failed connector effects and uncertain runs. The public authoritative EMPTY
transition is attempted before the provider-neutral compensator considers the
eligible failed-run subset. Emergency work revokes the recorded provider version,
checks connector name/ownership labels before stop/remove, then attempts DNS,
tunnel connections and tunnel deletion independently. Bounded stage failures
remain uncertainty. Successful emergency cleanup returns nonzero/non-authoritative
status, not normal acceptance. Name/label checking is not immutable container
custody against concurrent replacement; this file supplies no general adoption
or ambiguous retry policy.

Ingress-row decoding rejects duplicate identities, noncanonical references and
invalid version numbers after bounded SQL text projections. Other SQL/audit
reads fetch whole result sets without a global row/byte bound. Provider HTTP
uses a 20-second request timeout but unbounded response reads and default urllib
transport behavior. Cloudflare JSON evidence instead has a 64 KiB oversize
sentinel; protected inventory permits at most 20 pages of 100 selected records.
Tunnel deletion requires exact absence or a matching deletion tombstone plus
absence from the selected active query. Protected inventory comparison hashes
selected DNS/tunnel fields, not all provider state or concurrent history.

Audit correlation checks compare selected intent/correlation/version sets; they
are not exhaustive event-stream equality or a substitute for physical provider
verification. Secret checks inspect selected activity pages/markers. The outer
sanitized main suppresses ordinary failure text, while helper exceptions, raw
diagnostic fields and preserved causes require their own handling. There is no
single transaction spanning CPK, Docker, provider custody and Cloudflare.

The owning shell controls final fixture custody. In particular the Cloudflare
launcher has no abort-result-gated preservation: normal flow attempts fixture and
state-root deletion after failed abort cleanup. See the confirmed
[finding](https://github.com/OpenJ92/control-plane-kit-servers/issues/172#issuecomment-5630579917).
Controller cleanup logic does not repair that shell boundary.

This navigation was checked against selected consequential scenario, execution,
abort, transport and evidence paths, not a full audit of every helper or
transitive provider implementation. Read with the
[ordinary launcher](cpk_server_secret_provider_source_live_smoke.sh.md),
[Cloudflare launcher](cpk_server_cloudflare_secret_custody_source_live_smoke.sh.md),
[hosted workflow](cpk_server_hosted_activity.py.md),
[abort helper](cpk_server_source_live_abort.py.md) and
[abort tests](../products/cpk_server/tests/test_source_live_abort_compensation.py.md).
