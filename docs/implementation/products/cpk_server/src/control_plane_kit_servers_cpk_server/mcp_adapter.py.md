# `mcp_adapter.py`

Servers #397 composes released `mcp==2.3.0` low-level Server and its ordinary
Streamable HTTP ASGI application over the existing application boundary.
Core parity supplies stable tool names and route identity. A curated read-only
catalogue supplies explicit coordinate/query schemas and accurate annotations.
Operations retains semantic validation, authorization and durable read ownership.

The raw wrapper uses the existing bounded collector and strict decoder. It
authenticates before sensitive decode and places the verified identity in the
current ASGI request state. The SDK's request context carries that request to
each handler; no session caches identity. The SDK owns protocol versions,
discovery, envelopes, Host/Origin admission and transport lifecycle. Host startup
enters its manager explicitly. Stateless JSON mode supports both selected eras.

The handler validates wire argument shape, route budgets and existing closed
reobservation framing, then awaits the existing dispatcher. Owner errors retain
their bounded safe status/message in isError results; no exception text is added.
All owner outputs are measured before SDK result construction. Public owner
objects remain unchanged, including durable identifiers. Graph descriptions
explicitly identify redacted observations, not executable exports.

There is no custom initialize implementation, mutation replay, plan state
machine, resource framework, persistence, grant or credential installation.
The historical custom wire boundary remains separately at `/mcp/legacy`.
Source/client tests are not evidence of deployed compatibility or installed Codex
access. Full child acceptance and dependency resolution evidence remain in #397.
