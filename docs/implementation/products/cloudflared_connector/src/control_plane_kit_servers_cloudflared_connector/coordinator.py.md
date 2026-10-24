# Managed connector coordinator

Source: [coordinator.py](../../../../../../products/cloudflared_connector/src/control_plane_kit_servers_cloudflared_connector/coordinator.py).

Servers #188 adds a product-local main-thread process owner after merged PR278.
`run(configuration, *, token_path) -> int` validates configuration and an absolute
NUL-free token path before effects. Native starts in its own session, then the
existing immediately-binding SDK factory and serving thread. Stop is checked
between stages; created resources remain owned during partial-startup failure.
Private launch and raw diagnostic helpers are not a public supervisor API.

Frozen plan SHA2569f517197510a53cb4af9920082bc4c1508647ae3ebec00d2f7d46a71aac7e1ec
has actual Kepler and Meridian PLAN PASS. Validate before effects, use one native
process group and common SDK host, preserve first-stop7/8s deadlines and explicit
failure/forced-cleanup precedence. Exact child environment contains only the
validated token path. The optional raw diagnostic sink accepts an already
nonblocking pipe only, never changes shared flags, and may drop all diagnostics.
Token values, candidate paths and raw thread errors are excluded from records.

The coordinator retains first-stop timestamp/signal, sticky startup/host failure,
unexpected native exit and incomplete/escalated cleanup. Handlers record intent
only. CPython atomic dict.setdefault publishes the entire first time/signal/origin
fact once; a reentrant handler or interrupted internal stop cannot overwrite it.
The stop snapshot before native poll preserves observed-exit classification against
a signal delivered between poll return and classification. Actual health is invalidated before concurrent SDK/native cleanup. Serving
and shutdown threads are daemon threads with bounded main-thread observation;
never-started serving is not passed to stdlib's shutdown wait. Owned-thread errors
become fixed failure state rather than raw tracebacks. Listener close is prompt.
An entry gate cancels delayed serving before it invokes a closed host. If entry
was already admitted, closure waits for actual SDK serving or completion within
the same deadline, rather than confusing Thread.start with selector registration.
Deadline expiry forces closure and incomplete124; unrelated serving errors remain
sticky failures, not blanket-suppressed shutdown noise.

TERM/INT is sent to the owned group once, KILL at first-stop+7s if needed, with
final cleanup at+8s. Leader poll/reap and group absence are distinct observations;
permission/observation uncertainty is not absence. Forced/incomplete cleanup124
wins over sticky startup/host failure1, then unexpected native mapping. Native0
unexpectedly maps1; nonzero/signal results are preserved. No-child requested stop
returns0 without fabricating a child result; requested child0 requires clean
host/group completion. It does not establish lossless tunnel drain.

The launch helper uses fixed binary/metrics/native5s-grace argv, DEVNULL streams
and exactly TUNNEL_TOKEN_FILE in the child environment. It never reads token bytes.
The raw sink validates its owned non-inheritable duplicate and never changes
shared flags. Each closed ASCII record gets one write; full/failed/partial or
unsupported sinks drop it. There is no buffer, output worker, retry or flush.
Records may be wholly absent on blocking stderr and are not durable audit data.
The process owner excludes concurrent descriptor repurposing/flag changes.

Corrected24 targets at0e909260 received both TARGET PASS and CAUSAL-RED PASS:
54 connector methods collected,30 predecessor passes and44 intentional scaffold
errors, log866e80061d20e6f04dc883710f6c604d3a03b013517e19db4d733d6fe5bb3243.
This source checkpoint is not yet green; downstream target branches must execute
and actual source must be reviewed before the owning run. Image/PID1/descendant
reaping, actual process exit under undrained diagnostics and selected Docker
stop/profile/wheel proof remain later evidence. No publication/provider action,
connected-session drain or activation is claimed. Existing managed.py, reader and
historical image stay unchanged.
