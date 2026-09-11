Source: [tests/test_hosted_activity_readiness.py](../../../tests/test_hosted_activity_readiness.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These unit tests exercise the hosted workflow's response contracts and the public
convergence client's orchestration with patched HTTP/MCP calls and a small public
route fixture. They do not run a CPK server, deployment worker, Docker provider or
real gateway. Operations owns command semantics; the fixture supplies responses
and records requests rather than reproducing that state machine as its authority.

Claim tests require an immutable ClaimedRun with a strict positive generation,
closed response shape and matching execution request. Start and execute tests
carry the frozen generation, distinguish progressing/in-flight/completed from
stopped or malformed coordinator results, and prohibit another call after a
terminal/transport failure. Advance tests verify the submitted and returned
graph, realized projection, plan and desired-revision lineage. Persisted claim
state uses the same strict decoder. These selected invalid-value matrices do not
certify all possible hostile JSON or lease/concurrency behavior.

Plan and event reads must use both authenticated protocols and agree. Negative
cases cover missing/foreign fields, noncanonical or impossible timestamps,
duplicate/descending events, excess page length, extra fields and divergent
protocol results. A non-null next cursor is rejected by this single-page reader;
the tests do not establish complete arbitrary-length history traversal. Transport
failure wrappers preserve the original cause while bounding the public message.
The sanitized executable boundary suppresses a chained ordinary failure's output;
preserved exception causes are not themselves redacted for arbitrary callers.

The convergence fixture checks distinct operator/worker/approver credentials,
public route sequencing, fences, six desired-graph phases, router body digests,
retained node sets, destructive approval and no-op preparation without execution.
Selected observation/attention faults must stop rather than advance or blindly
redispatch. This is client request and report evidence, not provider effects,
actual authentication enforcement or durable restart recovery. Its descriptors
belong to the consumer-selected Core 087 contract; latest-upstream additions are
not automatically required fixture fields.

Readiness tests inject responses and sleep: first success has no delay, retries
sleep only between failed attempts, policy timeouts reach each request, and
exhaustion has no trailing delay. They do not measure wall-clock deadlines or
perform a real readiness check.

Navigation was checked against all test method bodies and selected fixture
support, the full [hosted owner](../scripts/cpk_server_hosted_activity.py.md)
and [convergence owner](../scripts/cpk_server_public_graph_convergence.py.md).
This is not a full audit of every fixture helper or transitive dependency.
Executable validation remains the repository's Docker-backed test suite.
