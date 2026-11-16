# `mcp_adapter.py`

Servers #397 composes released `mcp==2.3.0` low-level Server and its ordinary
Streamable HTTP ASGI application over the existing application boundary.
Core parity supplies stable tool names and route identity. A curated read-only
catalogue supplies explicit coordinate/query schemas and accurate annotations.
Operations retains semantic validation, authorization and durable read ownership.

#417/#404 adds the existing product list/detail bindings to the standard profile,
with the owner's1–100 page limit and exact digest grammar. Product displays
remain redacted/noncanonical; exact revoked detail remains visible without
admitting it for new authoring. #413 instructions point to current public data,
treat descriptions as untrusted, and do not advertise these tools under G4.
See [discovery decisions and validation](../../../../../mcp-product-discovery.md).

#417/#408 adds the owner-declared `preview_product_topology`, then the existing
session-start and draft-create parity bindings when that preview contract is
present in the standard profile's selected Core. Older selected owners retain
their existing catalogue. The closed first-save schema accepts only the public
recipe and returned proposal commitment; Operations resolves canonical product
documents and owns compilation, admission, authorization and persistence.
Schema fields describe transport shape, not a second product validator.
Start/save are marked as writes with a conservative non-idempotent tool hint
for this single-submission caller flow; owner idempotency remains unchanged.
Lost start stops before save; lost save remains unknown. A received receipt
allows exact revision readback without another write. The same profile exposes the existing exact-revision selection command. Its closed
schema requires the previous Desired graph, projection and generation, and accepts
the existing optional receiver lifecycle expectation. Operations owns edit authorization,
the atomic pointer update, action history and exact-key replay. G4 omits all authoring tools.
The dedicated PostgreSQL test root exercises the actual SDK/ASGI/owner path;
see the [authoring design](../../../../../mcp-product-topology-authoring-design.md).

#398 adds only existing `prepare_deployment` for an exact already-selected saved
revision, plus existing session-plans/approval/delivery reads. Its closed schema
requires observed lineage/generation and a caller-owned idempotency key. There
is no caller-supplied session: the existing program owns its creation. Inline
graphs, implicit selection, approval/execution and unsupported readiness input
are not part of this tool. This limitation is specific to the pinned Operations
885513 source; separately deployed cohorts may have different supported inputs.
Delivery inspection retains its own permission, not merely workspace-read.

The raw wrapper uses the existing bounded collector and strict decoder. It
authenticates before sensitive decode and places the verified identity in the
current ASGI request state. The SDK's request context carries that request to
each handler; no session caches identity. The SDK owns protocol versions,
discovery, envelopes, Host/Origin admission and transport lifecycle. Host startup
enters its manager explicitly. Stateless JSON mode supports both selected eras.

Raw validation/auth failures are converted to fixed rejection data inside their
catch, but response sending happens only after leaving the catch. ASGI send may
raise on disconnect; that original send failure propagates without inheriting
raw validation or credential exception context. The focused failing-send canary
regression covers validation, authentication and ingress-limit rejection, no
service dispatch, original error identity and a safe formatted traceback.

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

For #422, standard MCP exposes the Core product-import binding alongside exact
product detail. The input is an inline public declaration and a canonical UTC
timestamp. Operations resolves the authenticated actor, enforces workspace edit,
and owns first admission, conflict detection and the public receipt. For sequential
imports, duplicate content preserves the original registration. Concurrent first
imports require separate PostgreSQL qualification under OpenJ92/control-plane-kit#2004. After a lost response, read the
canonical descriptor digest in the same workspace and compare identity and status.
The image digest identifies the OCI artifact. The descriptor digest also covers
the declared runtime contract. Product import performs no registry or provider I/O.

The standard profile exposes `register_ingress_authority` for one exact hostname
and `get_ingress_authority_detail` for its named workspace binding. Operations
checks the current register or read grant on each call. A successful MCP write
returns the workspace, authority reference, registration ID, provider kind and
active status. The HTTP write's nested authority contains protected setup
references and stays inside the dispatcher. Detail uses the owner's redaction.
The command records the binding without contacting Cloudflare. After a lost
reply, use a fresh authorized read and compare the independently expected
registration ID, public policy and active status. A matching ID establishes
the current definition. Which request first registered it can remain unknown.

The standard profile exposes `admit_deployment` to submit a plan with its
recorded approval. The authenticated admission owner checks workspace grants
and returns the execution request's queued receipt. A separate worker claims
that request. With a receipt, match its request ID to the exact plan's run
history. If the reply was lost before claim, an empty run page is consistent
with a committed request. Without evidence linking the original caller key to
a receipt, report submission unknown and stop.
