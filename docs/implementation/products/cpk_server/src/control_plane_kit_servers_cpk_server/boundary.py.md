Source: [boundary.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py).
Maintain alongside the transport framing and selected Operations contracts.

The application boundary retains an actual configured CpkServerOperationsApplication
unchanged, including its authority mode, resolver and service objects. The existing
service-map input remains explicitly static compatibility. Sync and async dispatch
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

MCP's raw entrance receives the bounded host bytes, validates headers and authenticates
before strict JSON parsing. Duplicate members, non-finite numbers, non-object roots
and nesting above 64 are refused without service dispatch. The private admitted
path reuses that principal rather than authenticating twice. Mapping entrances
retain their existing header/auth/shape order. Trusted identity is
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

The six administration read routes have closed transport fields: target and after
are strict JSON objects; runtime_id and authority_ref remain percent-decoded text;
limit is a positive decimal integer. Operations still owns exact identity, required
fields, page limits, revisions and cursor semantics. Administration POST uses the
same strict JSON hooks, including finite float overflow and nesting refusal.
MCP administration arguments are measured against the matched request schema.

Both surfaces measure administration owner results against the matched response
schema before returning them. Escaped compact JSON measurement retains no complete
encoded copy and stops at the budget. The MCP result budget excludes its separate
JSON-RPC envelope, whose input remains capped by the existing envelope limit.
An invalid or oversized result produces fixed 503 `application response unavailable`;
the command may already have committed, so this is no rollback or retry claim.

These #341 changes address the reached transport targets and add actual-host
forwarding/raw-parse evidence. Source review and the owning gate are pending.
They do not complete dynamic factory/startup, management selection or invocation
composition, and establish no live adoption.

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
## #351 provider-policy framing

The accepted AUTHORIZATION route family retains existing authentication and
request/response budgets. Its list query has a closed set of plain string filters
and integer limit; detail and command reads have an explicitly empty query set.
Empty sets do not fall through to generic pagination. Duplicate, unknown and
malformed fields are refused before dispatch. Operations owns semantic policy,
binding admission, durable commands and current-provider result validation.
