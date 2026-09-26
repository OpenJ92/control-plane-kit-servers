Source: [boundary.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py).
Maintain alongside the transport framing and selected Operations contracts.

The application boundary retains one service map and constructs the actual
CpkServerOperationsApplication over those same objects. Sync and async dispatch
delegate to that owner's handle and handle_async respectively. HTTP/MCP process
entrances share request preparation with their synchronous counterparts and
share result/error normalization. The host awaits completion; cancellation is
not caught because normalization handles Exception, not BaseException.

HTTP preserves route matching then authentication before payload decoding. MCP
preserves host JSON parsing followed by header validation and authentication,
then validates object shape before inspecting the method. Trusted identity is
provided only by the configured verifier. Operations owns workspace/kind/scope
authorization and canonical command construction.

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
