# Source-live public transport evidence

This test runs within the established Servers Docker suite. A local HTTP responder
observes the actual authenticated MCP envelope for reads and commands. It proves
explicit identity forwarding, status-only HTTP refusal, bounded MCP failure
messages and refusal to redirect an authenticated request.

The responder owns no workspace or policy state. This is transport evidence, not
the two-workspace process scenario, permission admission, provider execution or
deferred in-flight revocation acceptance. No production concurrency is changed.
