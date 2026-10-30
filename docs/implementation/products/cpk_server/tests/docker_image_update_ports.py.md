Source: [docker_image_update_ports.py](../../../../../products/cpk_server/tests/docker_image_update_ports.py).

The runtime recorder delegates once and returns the genuine result. The public
transport correlates original step_started and step_succeeded events; coordinator
PROGRESSED activity_id names the next ready activity and cannot prove completion.
A post-response hook fault returns the original success to the normal client
journal, latches a terminal fixture error, and refuses any next mutation before
HTTP dispatch. No production scheduling, retry or owner-state changes occur.

#254 adds an optional fixture observer after genuine public event correlation,
commit recording and required startup attachment. It shares the same fault
latch: the original response reaches the client journal even if observation
fails, and subsequent mutation is blocked. The observer receives the actual
runtime record and public response; it does not manufacture receipts or advance
owner state. The later coupled witness will use it only for bounded reads between
the committed workload effect and the next gateway effect.

The coupled source dry run identified one missing fixture connection: a gateway
replacement must refresh the reader's exact observed binding after its public
commit, just as a gateway start does. The existing checked `placement.completed`
path now also receives gateway `ReconcileNode`; other replacements do not enter
its startup-image path. This only observes the returned container and updates
the fixture reader binding. It does not attach a network, replace a resource,
alter execution evidence or advance the graph.

Both public event commitments must match the owner-defined STARTED/SUCCEEDED
values for the genuine request's run/activity, attempt one, actual worker and
public claim generation. The existing intent/result/state fingerprint helpers
compute these assertions; this fixture does not fold or write attempt state.
The installation receipt reader validates full request/selection correlation,
REPLACED disposition and owner-defined fingerprints of the observed prior/current
Docker container IDs. The scenario joins that same genuine result to public
update history, so transformed or rejected outcomes cannot pass this assertion.

The ingress resolver/transport explicitly substitute DNS and public routing.
Original numeric destination, Host, SNI, path and receiver envelope are checked
before an actual bounded socket send to the fresh bound Gateway. No request can
fall through to the synthetic public IP. Gateway/SDK signing and decoding remain
real; LocalGatewayHealthClient is unchanged. This does not prove public TLS/DNS.

The transport accepts HTTPX's normalized default HTTPS port (`None`) as 443,
while retaining the separate HTTPS condition and all exact host, SNI, method,
path and signed-target checks. Nondefault ports remain refused. The first
package run exposed the former literal-443 check as a fixture defect before
any live request was dispatched.

Failed apply diagnostics use only existing authenticated `read.run-events` and
`read.plan-runs` through the bounded public pager. Output keeps at most the last
32 events, bounded identifiers/failure codes, closed event/run/category values,
and client/fixture-failure classifications. Payloads, failure messages/details,
metadata, credentials and exception text are excluded, except the exact public
`failure.details.effect_outcome.runtime_failure_code` classification leaf.
The selected Operations owner admits that leaf as a bounded symbolic code; no
surrounding details or outcome semantics are copied. Output is capped at 32 KiB
with a fixed small fallback, including after partial-read failure. Failure codes
are owner-provided strings filtered to bounded tokens, not a closed enum or a
general secret sanitizer. The emitter treats serialization/output as best-effort
so reporting failure cannot replace the primary execution failure. It returns
an explicit boolean emission outcome; failed projection returns the fixed
unavailable classification, with no silent exception handlers.
A failed evidence read returns a fixed unavailable classification without
raising or changing the original result. Missing client results are reported
without guessing a run or issuing reads against a previous apply.

The diagnostic domain includes unverified execution/advancement and unchanged
advancement so unexpected reconstructed-replay classifications remain precise.
The same bounded public reporter is reused; no additional observation protocol
or secret-bearing fields are introduced.

The #342 declaration-cutover stop lacked the actual execute response or transport
classification. The existing attachment now retains only its last execute-call
observation: fixture-wide ordinal, request run ID, elapsed milliseconds (clamped
at one hour), already-recorded runtime completion count during that request,
received-response count and unsent-mutation count. A response projection retains
only closed coordinator/run statuses, bounded effects count/activity ID, and
whether the response run matches the request. It records an unsupported/running
response faithfully even when the maintained client cannot accept that shape.
It does not reinterpret that response or change client acceptance.

Transport failure categories come from the immediate exception context's type
and, for HTTP errors, numeric status only. URL, exception message, body, headers,
query, credentials and context objects are never retained in the diagnostic.
Unrecognized/response-size failures remain unclassified; no timeout is inferred
from elapsed time. Observation failure yields unavailable evidence and preserves
the original response or exception. The public failure report includes this
observation only when its request run matches the failed result, so a previous
apply cannot supply evidence for a later one. All counters describe this fixture
only; they are not independent provider I/O measurements. Existing timeouts,
dispatch count, fault latch, owner semantics, assertions and cleanup are unchanged.
#253 retains only `(target_id, health_kind, HTTP status)` from the real forwarded
health response so the existing witness can correlate signed readiness with its
replacement phase. Credentials, request bodies and response bodies are never
recorded. The existing transport test checks these observations alongside host,
SNI, path and forwarded-byte preservation.
