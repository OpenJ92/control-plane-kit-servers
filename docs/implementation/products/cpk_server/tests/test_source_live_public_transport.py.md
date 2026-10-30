# Source-live public transport evidence

This test runs within the established Servers Docker suite. A local HTTP responder
observes the actual authenticated MCP envelope for reads and commands. It proves
explicit identity forwarding, status-only HTTP refusal, bounded MCP failure
messages and refusal to redirect an authenticated request.

Scenario orchestration checks use a recording client double only to establish
that the scenario cannot approve an unexpected destructive plan, retry an
uncertain application, or accept a different run from the subsequent public
status read. They do not reimplement deployment or admission state machines.
The actual client workflow and owning public process suites establish those
boundaries; the G workload composition remains separately required.
The isolation regression uses the installed owner's `GraphPointerReadModel`
descriptor, which has no workspace ID, and verifies that both surfaces reach
the foreign graph/plan/run attempts after checking identity through
`read.workspace`. It is response-shape composition evidence, not a live denial.

The responder owns no workspace or policy state. This is transport evidence, not
the two-workspace process scenario, permission admission, provider execution or
deferred in-flight revocation acceptance. No production concurrency is changed.
