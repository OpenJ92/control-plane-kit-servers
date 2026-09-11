Source: [scripts/cpk_server_public_graph_convergence.py](../../../scripts/cpk_server_public_graph_convergence.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This public-client scenario compiles Hello/router graphs and submits injected
CPK read/command calls. Disposable phases are initial, multi-add, rewire, subset
removal, no-op and teardown. Retained mode submits one application graph with an
existing tunnel-token reference; it creates no NamedPublicIngress or tunnel/DNS
authority.

Distinct operator, approver and worker credentials serve selected routes.
Transitions read lineage, prepare, inspect plan/approval, decide, admit, claim,
start, execute one effect per step and advance only after reported success,
then read graph/run/event/observation evidence. Uncertain or non-progressing
results return attention-required; failed/ambiguous calls are not repeated.
Fresh invocation UUIDs make keys local to one invocation, not crash-resume keys.

Direct function use assumes the fixed scenario, including removals, is already
authorized; CLI switches add explicit transition/destructive gates. Retained
mode separately requires destructive consent when returned approval requires
it and checks prior public plan/run truth before another submission, including
completed no-op preparation with distinct desired coordinates. These checks
do not replace server authorization or concurrency control.

Router verification includes an exact rendered Hello-response digest. Reports
distinguish current-run observations from unchanged-router historical evidence
now marked stale. Retained edits without a router check record unknown/not-observed.
A no-changes plan does not create another activity run.

Calls have a between-request thirty-minute budget, bounded execution steps and
sixteen pages of at most one hundred rows; cursor size/repetition are checked.
MCP streams at most 2 MiB and maps selected errors to bounded categories. The
CLI disables ambient proxy trust and redirects. Returned fields and JSON-RPC
identity are not exhaustively validated. A blocking call can overrun the
between-request budget; there is no general cancellation.

The final report selects public plan/approval/outcome/event fields, omits graph,
environment and provider-event payloads, and is size-checked, exclusively created
mode600 and fsynced with its directory after execution. It is not incremental
durable history: a crash/write failure can leave effects explained only by the
server. Selected public fields are trusted, not universally sanitized.

Bootstrap writers generate separate random principals and a database password.
Persistent bootstrap copies existing provider authority and assigns its file to
UID/GID10001; it does not issue that authority. Exclusive files limit overwrite,
but multi-file bootstrap is not transactional and only selected persistent files
are fsynced. Fresh caller-owned directories remain a custody assumption.

Related source: [launcher](cpk_server_public_graph_convergence_smoke.sh.md),
[Hello rendering](../products/hello_server/src/control_plane_kit_servers_hello_server/server.py.md),
[client tests](../../../tests/test_hosted_activity_readiness.py).
