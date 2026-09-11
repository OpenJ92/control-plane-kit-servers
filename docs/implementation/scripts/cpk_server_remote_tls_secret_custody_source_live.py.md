Source: [scripts/cpk_server_remote_tls_secret_custody_source_live.py](../../../scripts/cpk_server_remote_tls_secret_custody_source_live.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This controller separates deploy, resume and prepared-denial phases. It admits
provider/reference metadata through public CPK routes, writes TLS/OCI material
directly to the fixture provider, registers remote Docker authority and drives
HostedWorkflow with runtime-network synchronization disabled. Neither controller
nor CPK needs a host socket in the paired launcher; the host shell owns DinD.

Deploy records graph/run coordinates after public success. Resume requires the
current graph ID still match, then performs an update and empty-graph teardown.
The shell recreates CPK/Secrets around that boundary while retaining their stores.
The Hello descriptor deliberately removes semantic verification without changing
its product identity; step mentions and graph success do not establish remote
application health or published-contract parity.

Denials cover foreign workspace, wrong intent, revoked CA version and unavailable
provider. Preparation persists a started run with frozen ClaimedRun; execution
uses at most forty calls and stops on selected terminal/attention outcomes.
It requires no current-graph advancement, an expected code somewhere in rendered
terminal/events and selected secret-marker/token absence. That is not exact
causal-event validation or proof of zero daemon mutation; the shell separately
compares inventories and correlates authorization/provider records.

State writes overwrite directly, then chmod600. There is no atomic replacement,
fsync, size cap, closed document schema, symlink custody or concurrent-writer
protocol. ClaimedRun reconstruction protects only its selected nested fields.
The phase file is not an exactly-once effect receipt or a general recovery API.

Provider POSTs read bootstrap material and use twenty-second urllib timeouts,
but response reads are unbounded and redirects/ambient proxy behavior are not
closed here. Write success checks stored outcome, not an exact version receipt;
revoke success checks HTTP200 plus a mapping. Public metadata checks compare
selected sets/markers over the first page, not every possible secret encoding.
Sanitized main hides ordinary final exception text, not all upstream output.

Related source: [launcher](cpk_server_remote_tls_secret_custody_source_live_smoke.sh.md),
[hosted workflow](../../../scripts/cpk_server_hosted_activity.py),
[fixture assertions](../../../products/cpk_server/tests/test_image_bootstrap.py).
