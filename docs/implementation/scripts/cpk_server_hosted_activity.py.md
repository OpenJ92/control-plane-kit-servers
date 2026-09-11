Source: [scripts/cpk_server_hosted_activity.py](../../../scripts/cpk_server_hosted_activity.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

HostedWorkflow is a smoke-controller client of public workspace, catalogue,
authority, approval and deployment HTTP/MCP routes. It also supplies shared
claim/result decoders to other controllers. Its fixed operator/worker credentials,
actors, clock and scenario workspaces are fixture defaults. Actor/scope fields
describe requests; server authentication and authorization remain authoritative.
run_approved_transition automatically approves the prepared transition as part of
the harness: invoking it requires authorization for the scenario's effects.

The sequence is session, fenced desired graph, plan, visible approval request,
approval decision, admission, claim, start, execute, current-graph advance and
readback. Desired/plan coordinates are held in memory, not a recovery journal.
ClaimedRun freezes a bounded run ID and positive integer claim generation; start,
execute and advance reuse that generation. Their closed result validators check
corresponding IDs/statuses and, for advance, graph/projection/revision coordinates
and digest shape. They are explicit response contracts, not a complete hostile
JSON validator for every route. An execute run permits at most 80 one-effect
calls, stopping on failed, unsupported, uncertain or blocked; exceptions stop
without redispatch. Per-call timeouts and attempt caps are not a whole-run deadline.

Plan detail and run-event reads compare HTTP and MCP results and validate selected
closed shapes, timestamps, sizes and identities. An event page must have no next
cursor, unique IDs/ordinals in sorted order and at most the requested limit;
ordinals need not be contiguous. Activity assertions find selected successful
node/runtime steps, not a complete causal trace. The general HTTP helper reads
at most 1 MiB without an oversize sentinel; MCP checks an object result/error,
not the complete JSON-RPC envelope. Helpers can include bounded server error
text in exceptions; the executable's sanitized main replaces ordinary failures
with a fixed message, without sanitizing every caller or BaseException.

Graph builders use decoded published product values and the consumer-selected
Core 087a892 contracts. Hello, router switching, multiplexer observation,
Postgres retention, public ingress toggling and authenticated private probing
are separate scenarios. Socket edges, runtime authority references, named
ephemeral ingress and delegation authority bindings remain topology values;
planning/execution perform their effects. Public-environment replacement only
permits declared names. Postgres/private gateway builders explicitly empty
selected verification contracts without changing product identity, so graph
completion is not unchanged published-product health acceptance.

Authority helpers register local Docker, pull and ingress metadata. Provider
registration/delegation admission checks selected public key metadata against the
expected issuer/key/hash/reference; it does not put private key bytes in those
requests. The ordinary Cloudflare helper and several scenario probes are legacy:
unsigned HTTP/Postgres gateway probes cannot establish current authenticated
gateway acceptance; the Postgres bodies also omit the current explicit null path.
The separate signed helpers bind canonical request digests and Ed25519 grants.
The immediate replay check only checks one live-process first/second request,
not expiry/skew or restart replay durability.

With network synchronization enabled the controller uses ambient Docker authority
to attach itself and the named CPK container to all matching workspace/runtime
networks, confirming attachment; disconnect forcibly detaches them. These effects
are outside operation history and lack an exact-run custody journal. Public HTTPS
connects to a resolved IPv4 address while preserving verified TLS hostname/SNI;
DNS fallback queries Cloudflare. A failed/non-ready reachability check after
teardown is not provider-side DNS/tunnel deletion evidence. Retained-volume checks
establish continued existence by name, not preserved database contents. Selected
activity/response substring scans are not universal secret-redaction evidence.

Read with the [launcher](cpk_server_hosted_activity_smoke.sh.md),
[convergence controller](cpk_server_public_graph_convergence.py.md),
[process admission](../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py.md)
and [readiness tests](../../../tests/test_hosted_activity_readiness.py).
