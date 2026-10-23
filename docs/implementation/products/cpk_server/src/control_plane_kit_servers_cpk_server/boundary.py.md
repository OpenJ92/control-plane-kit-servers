Source: [boundary.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py).
Maintain alongside the transport framing and selected Operations contracts.

The application boundary retains one service map and constructs the actual
CpkServerOperationsApplication over those same objects. Sync and async dispatch
delegate to that owner's handle and handle_async respectively. HTTP/MCP process
entrances share request preparation with their synchronous counterparts and
share result/error normalization. The host awaits completion; cancellation is
not caught because normalization handles Exception, not BaseException.

HTTP preserves route matching then authentication before payload decoding. Its
stream entrance shares the private immutable admission value with the existing
byte entrances: route, path pairs and verified principal. No public entrance
accepts an admission value or trusted principal. Unknown routes and invalid
credentials return before any stream pull; an accepted request authenticates
once. Commands reject nonempty queries before collection and use the route byte
budget. Reads reject the first nonempty body chunk before query validation,
retaining no body. Completed empty reads retain their query grammar and budgets.

MCP preserves bounded host JSON parsing followed by header validation and authentication,
then validates object shape before inspecting the method. Trusted identity is
provided only by the configured verifier. Operations owns workspace/kind/scope
authorization and canonical command construction.

MCP resolves the name through parity or HTTP-route fallback, then rejects Core's
HTTP_ONLY_COMMAND_ROUTE_IDS before retrieving or copying arguments. Unknown and
HTTP-only operations return the same fixed 404. Canonical bindings and the
independent Operations guard remain unchanged. Standard service-request repr
omits payload on both surfaces; this is not an asdict or arbitrary serialization
guarantee. Confidential provision is still unavailable in production through #316.

Read query decoding is route-local transport framing. Existing paged reads keep
the closed `limit` integer and `after` JSON-object grammar. The receiver
authoring-context route instead admits only strict JSON `expected` and
`pending_draft` values, passing their semantic type, pin and lineage validation
to Operations. Strict percent decoding, duplicate names after decoding,
duplicate JSON members, non-finite numbers, excessive nesting and encoded query
size fail without reflection. Authoring fields cannot enter unrelated routes;
pagination fields cannot enter the authoring route. Authentication still occurs
before any sensitive query decode, and GET bodies and command queries remain
forbidden.

Connector reobservation uses one transport-only allowlist: activity_id,
prior_attempt, claim_generation, idempotency_key. HTTP takes workspace_id/run_id
from the route and rejects them in the body; MCP requires both in its arguments.
Unknown or missing fields fail before dispatch. The declared schema byte limit
bounds HTTP body and encoded MCP arguments. The schema names do not provide
field validators: Operations owns all numeric, identity and idempotency laws.

CpkServerApplicationError retains its public bounded response. Known public
InvalidOperationCommand and InvalidEffectRecoveryContract errors become a fixed
400 without exception text. Unexpected failures remain a fixed500. No durable
state, retry/lifecycle policy, signing, provider or credential effect belongs to
this boundary. The recording-coordinator ASGI tests prove transport composition;
they do not qualify images, provider behavior or persistence.
