# Standard MCP operator connection

Source checkpoint for Servers #396/#397; focused source validation passed.
Accepted base: `2093f5182748a4aca638f362eece0bc4f063a1db`,
`roadmap/1813-runtime-control`, accepted in PR #395 comment 6840942585.
The isolated branch is `codex/396-standard-mcp`.

## Selecting a saved revision as Desired

In the standard authoring profile, use `get_desired_topology_draft_revision` to inspect the exact
target. You can choose an older revision if its products are still active and its secret and
receiver references still pass the workspace’s admission checks. Read `get_workspace`
for the **existing** Desired graph ID, realized projection ID and generation. Supply those three
values as the expected state to `select_desired_topology_draft`, alongside the workspace, draft,
revision, open session ID and a fresh key for this intent. For the first selection, explicitly
supply null for both IDs and zero for the generation. Workspace edit access is required.

Keep the receipt. Confirm the selected graph and realized projection with `get_desired_graph`
and the new generation with `get_workspace`. A competing selection makes the old expectation
stale, even if the graph later returns to the same value. Selection leaves Current in place.
Planning and deployment are separate actions. If the reply is lost, read back the pointers.
Even a match cannot establish which request set them. Leave the request outcome unknown and
do not automatically submit it again.

## Selected behavior and smallest missing connection

At this base, `server.py:create_app` installs POST `/mcp` and the HTTP routes over
one `CpkServerApplicationBoundary`. `boundary.py:CpkServerMcpProcessBoundary`
collects a bounded raw envelope, authenticates, strictly decodes JSON, resolves
Core parity names and awaits the existing Operations application. Its
`resources/read` name/arguments format and raw result envelope are CPK-specific;
an ordinary client cannot discover the tools. HTTP already supplies the usable
application path. No planner, authorization service or durable store is missing
from this transport design.

Selected package coordinates remain Core `7afef43f`, Operations `885513e3`,
Interpreters `685c8627`, server SDK `220f6316`, Secrets `09442303`, as recorded
in `coordinates/server-products.json`. These source selections are not claims
about the deployed grandparent's cohort or an installed Codex connection.

## Selected composition

Current evidence: PR #400 was accepted at source
`8b8e87c43c31d7afadda72302a6cddca744e3a8e` and merged as `a2b10cbc`.
Its full owning gate passed 1,373 unit checks, the packaged PostgreSQL
preparation/response-loss/reconnect and receiver-restart witnesses, downstream
checks and final cleanup audit. Hosted run `43377819873` passed the same source.
The chronological #398 failures below remain historical evidence; the earlier
Hello listener failure did not recur and its cause remains unresolved.

The additive #401 grandparent source has focused default169 and grandparent174
PASS evidence. Its current full package gate and PR CI remain outstanding;
deployable grandparent artifact, existing-state replacement and installed Codex
connection remain separate, uncompleted boundaries. See
[the compatibility record](grandparent-mcp-compatibility.md).

Use official `mcp==2.3.0` (release source
`2118f14f8a19bc158d8a1cf90af58d85d187f849`) without CLI extras. Its low-level
`Server` accepts explicit schemas and standard results; its normal Streamable
HTTP ASGI application owns discovery, protocol negotiation and lifecycle.
The selected release supports both modern 2026-07-28 discovery and the 2025
initialize lifecycle. Qualify both with the actual released client rather than
assuming initialization is required for every revision.

Standard `/mcp` replaces the historical wire endpoint. Preserve that historical
format at explicit `/mcp/legacy`; migrate maintained source callers to that URL.
Historical published-image callers keep their original endpoint when selecting
an older image. Do not select wire behavior by guessing from message shape.

The new adapter keeps the inclusive raw-envelope cap and authentication before
strict decoding, then passes the admitted request to the SDK. The SDK receives
the replayed bounded bytes, not a second network read. Request-local ASGI state
holds the verified principal; no identity is retained in an MCP session.
Use the SDK's Host/Origin protection, exact `/mcp` routing, JSON responses and
stateless HTTP; each host lifespan creates a fresh SDK transport/manager pair
and enters the returned SDK application's own lifespan. SDK managers are
single-use; the CPK application, services and request authentication persist
across sequential host lifespans.

Initial discovery is a curated operator catalogue: workspace/current/Desired,
saved drafts/revisions and their preparation/attempt history, plan/run/history
reads and permission/runtime inspection. A dependent command slice adds the
existing session/preparation path using the saved revision identity. Explicit
argument schemas describe coordinates and owner inputs; owner result objects
remain unchanged. Descriptions label public graph views as redacted observations,
not source exports. HTTP-only confidential intake is absent from discovery and
call dispatch. Tools do not provide approval, grant scopes or execute a plan
implicitly.

Calls enforce route input/output budgets and closed reobservation framing, then
reuse the awaited application dispatcher and bounded error mapper. Return the
owner's safe result or error/status using SDK `CallToolResult`; preserve server
plan/session/history references. JSON-RPC IDs correlate one exchange only.
Caller idempotency keys and durable queries retain their existing ownership.
An unavailable response does not imply rollback or permission to redispatch.

## Laws and evidence plan

| Law | Existing proof and classification | New proof |
| --- | --- | --- |
| Authentication before sensitive decode; bounded raw collection | `test_confidential_transport.py`, preserved | Standard endpoint raw duplicate/nonfinite/depth/overflow cases, no dispatch |
| Dynamic authority and safe errors | `test_http_mcp_boundaries.py`, preserved | Real application denial through SDK; changed credentials on subsequent requests |
| Awaited execution and cancellation | `test_awaited_execution_host.py`, preserved | Standard dispatch remains awaited; concurrent principals remain isolated |
| HTTP/MCP owner parity | `test_revision_history_composition.py` and acceptance tests, preserved | Actual SDK discovery and authenticated workspace/graph/history reads match HTTP |
| Route budgets and confidential exclusion | Boundary laws, strengthened on standard path | Every advertised route bounded; confidential route unavailable |
| Protocol mechanics | New | Released client auto and legacy modes, exact endpoint, Host/Origin and host lifespan |
| Saved-revision preparation | Existing Operations owner, composition proof only | Dependent slice uses actual owner, precise denied permission/admission and unchanged durable references |
| Installed Codex connection | Not established | Separate qualification and explicit credential/connection release |

Focused target-red precedes implementation. Proposed owning entrance:
`./test.sh --mcp-source-tests`, retaining policy/support/integrity, the established
Dockerfile.test dependency installation, compile/import and focused product
tests. No socket or external effects in the test container. The completed
combined boundary requires one owning gate after independent source review.
Apparatus failure stops; no replacement runner or unreviewed repair.

## Limits and handoff

Meridian is the independent reviewer; North owns coordination and acceptance.
No Core/Operations semantic changes, new persistence, client journal framework,
live credential installation, service replacement, publication, #163 mutation
or #391 restart is included. Final combined package validation and installed
Codex qualification remain outstanding.

## #397 focused evidence

`./test.sh --mcp-source-tests` completed exit 0 at
`bcbf02692f7fa9a29c49ea76db2ba8b56676ec5a`: 26 support and 78 selected product
tests. The actual released SDK client negotiated auto `2026-07-28` and legacy
`2025-11-25`, discovered the read tools and performed authenticated reads. Actual
CPK read owners produced workspace/Desired/saved-revision/history results matching
HTTP over immutable record-return fixtures, including redaction and stable saved
identity. Concurrent identities, changed credentials, strict raw framing,
sanitized SDK diagnostics, route budgets, confidential exclusions, Host/Origin,
lifespan and explicit caller migration passed. Prior failing runs remain in the
issue history. This is source composition, not PostgreSQL persistence or an
installed Codex connection. [Terminal evidence](https://github.com/OpenJ92/control-plane-kit-servers/issues/397#issuecomment-6843099429).

Official references: [SDK ASGI integration](https://py.sdk.modelcontextprotocol.io/run/asgi/),
[SDK protocol versions](https://py.sdk.modelcontextprotocol.io/protocol-versions/),
[Codex MCP setup](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Known caller migration

The framework-neutral legacy boundary API is unchanged. Source host tests and
current composition acceptance callers use `/mcp/legacy`. The maintained image
smoke selects that path for wrapped source/current artifacts, retaining `/mcp`
for its explicit historical `published-baseline` profile. An explicit closed
`CPK_LEGACY_MCP_PATH` override also supports older retained wrapped artifacts.
The hosted-activity and graph-convergence scripts default to `/mcp/legacy`;
when intentionally targeting a pre-#397 image, set
`CPK_LEGACY_MCP_PATH=/mcp`. Only these two literal paths are admitted; no automatic
fallback or mutation redispatch occurs. The hosted-activity shell launcher
defaults explicitly to `/mcp` for its existing historical catalogue image and
forwards a supplied override; the convergence launchers forward their explicit
selection too. They remain legacy callers, not the
ordinary-client interoperability witness. Retirement requires a later decision;
there is no guessed end-of-support date.

## Prepared Codex configuration (#399; not installed)

The #401 grandparent compatibility source introduces an explicit server exposure
selection, `CPK_MCP_PROFILE=grandparent-read-only-v1`. It registers only workspace,
Desired, exact saved revision and revision-attempt reads; it does not register
`prepare_deployment`, and direct command calls cannot bypass this catalogue.
Unknown profile values refuse configuration. The default `standard` profile
retains the #400 catalogue and preparation contract. This source selection is
not a dependency-version guess or an authorization grant. Grandparent managed
HTTP composition, artifact qualification and installed-client evidence remain
separate acceptance claims until their owning checks complete.

After source qualification and approval of the actual endpoint, credential
reference and scopes, a local Codex host can use its normal configuration:

```toml
[mcp_servers.cpk]
url = "http://127.0.0.1:18163/mcp"
bearer_token_env_var = "CPK_MCP_BEARER"
enabled_tools = ["get_workspace", "get_desired_graph", "get_desired_topology_draft_revision", "list_desired_topology_draft_revision_attempts"]
default_tools_approval_mode = "prompt"
```

This is a preparation example, not a live access claim. The endpoint must serve
the reviewed adapter; older deployed images still speak only the legacy format.
Supply the approved scoped bearer privately through the named environment
variable; never put its value in the configuration, repository or chat. Use an
approved workspace ID and exact saved revision for the first authenticated read.
Confirm discovered schemas and results after the client's normal reload/new
connection. Reading a public graph does not return original source bytes.

Removing this configuration table and its privately supplied environment binding
disconnects the client after reload; it does not revoke server-side credentials
or change permissions. Any credential installation, grant or live connection
verification remains the separately approved #399 boundary. SDK source tests
alone cannot complete that issue.

## Saved-revision planning

The standard MCP tool `prepare_deployment` uses the same Operations planning
service as HTTP. Supply the workspace, selected draft and revision, observed
Current and Desired authored graph and projection IDs, Desired generation, title
and a caller-owned idempotency key. Operations creates the preparation session
and returns its planning status, plan ID and any approval-request ID.

Omit both readiness fields for ordinary planning, or supply one of the following.

| Field | Accepted value |
| --- | --- |
| `http_verification_intent` | `authenticated-samples` |
| `managed_verification` | `authenticated-local-postgres-and-http` |

The readiness choice is part of the durable intent. Reusing the key for the
identical request returns the stored result. Changing the choice under that key
produces a conflict. Operations can return a `review-blocked` plan for an
unsupported graph. The restricted `grandparent-read-only-v1` profile exposes
inspection only.

The supported operator sequence is:

1. Inspect workspace/current/Desired and the exact saved revision. Compare the
   immutable identities and generation; public graph descriptors are redacted.
2. Check required authority: workspace edit and `plan:request`. Delivery
   admission is a separate owner prerequisite for graphs that require it.
   `list_runtime_authority_deliveries` exposes existing redacted metadata only
   with its own `runtime-authority-delivery:read` scope. A denied diagnostic says
   nothing about whether a delivery exists.
3. Retain the exact intended fields and domain idempotency key before requesting
   preparation. A JSON-RPC request ID correlates only one exchange. Neither a
   tool annotation nor a client prompt grants CPK authority.
4. Inspect `get_plan_detail` and, when present, `get_approval_detail`. Preparation
   does not approve or execute. Domain errors preserve existing bounded status
   and messages; a generic owner conflict is not relabeled with an invented cause.
5. After reconnect, use known durable references. Existing revision preparations
   expose associated session IDs, `list_session_plans` exposes their plans, and
   plan detail/runs/events expose retained outcomes. These are observations,
   not retry permissions.

There is no new public lookup by preparation idempotency key. If an entire
response is lost and several preparations could match, association can remain
ambiguous; do not choose the newest/sole-looking record in general or blindly
resend. An unavailable result or cancellation is not proof of rollback.

The source tests use actual command construction and permission checks with a
recording program port. The accepted final durable witness extends the existing
packaged PostgreSQL smoke: explicit fixture selection once, one ordinary SDK
preparation, injected response loss, reconnect and owner queries. Its known
single-fixture association is not a general concurrency/recovery guarantee.
PR #400 completed packaged persistence qualification and combined acceptance;
that result does not qualify the later #401 changes or a deployed grandparent.

### Historical implementation attempts (before PR #400 acceptance)

The first ordinary gate at `e778fbc` passed all 1,369 unit tests and reached the
new packaged witness, then stopped: the deliberate response-loss exception also
escaped the SDK client context teardown. Reconnect assertions were not reached,
so no durable-outcome qualification follows from that attempt. The narrow
test-only successor catches only its dedicated injection subtype across the
whole context; unmatched errors propagate. A focused SDK lifecycle regression
and renewed packaged/owning execution still require terminal evidence. No
product behavior, source pins or response-loss assertions are weakened.

The corrected ordinary run at `a0a2ab3` passed all 1,370 unit tests but stopped
earlier in the existing source-built Hello declaration-family listener check.
Its last readiness category was transport-unavailable; the recorded evidence
does not identify which role or underlying transport condition failed. The MCP
PostgreSQL witness was not reached. No retry, timeout increase, apparatus repair
or hosted substitution is implied. The narrow source-only diagnostic successor
adds fixed role/category reporting without raw URLs, headers, messages or
payloads; polling, assertions and cleanup are unchanged.

Independent review also identified exception-context disclosure when a send
failed while raw validation/auth errors were active. The successor defers fixed
rejection sends until after the catch and adds an actual ASGI failing-send canary
regression. This is a source finding, not evidence of a deployed leak. Focused
successor qualification and the next owning-gate disposition remain pending.

The `2600a3e` focused run passed 113 checks with independently recovered exit 0.
Its ordinary full run passed all 1,372 unit checks, both wrapper families,
Secrets initial/restart checks and the packaged MCP PostgreSQL preparation /
response-loss reconnect query. It then exited 1 during receiver acceptance:
the existing authority witness enters the same restarted host twice, while
the cached SDK manager rejects a second lifespan. The former listener failure
did not reproduce; its cause remains unresolved and its evidence is retained.
Later full-suite phases and the final audit were not reached.

The test-only `461bda7` regression reproduced the exact second-lifespan error
through the focused Docker selector (exit 1; nine other MCP tests and 26 support
tests passed). It retains one real host and checks credential denial without
service dispatch plus released-client discovery/read in both protocol eras on
each lifespan. The bounded successor creates a fresh paired transport/manager
through the SDK public factory and enters its own lifespan; it does not reset
SDK internals, rebuild CPK management state or weaken the receiver witness.
At that checkpoint focused green and independent source review were pending;
the later `8b8e87c` source and PR #400 acceptance closed those source/package
requirements. That historical correction did not itself authorize a full retry.

## Create a workspace and grant access

In the standard profile, authenticate as a configured installation administrator.
Use an operator-approved workspace ID, principal and set of scopes. Workspace
edit or deployment approval alone does not authorize administration. Each call
uses the identity that authenticated that request.

1. Call `create_workspace_as_administrator` with the new `workspace_id`, a
   display `name` and a caller-owned `idempotency_key`. Optional `metadata` is
   public workspace data. Keep the returned creation receipt, including its
   installation ID, workspace ID, actor and observed Current graph ID. Creation
   initializes the empty workspace and grants nobody access.
2. Use `inspect_workspace_permission` with that workspace ID and the exact
   target (`issuer`, `subject_id`, `kind`). As the authorized administrator,
   confirm the current revision or the absence of a record.
   `list_workspace_permissions` lists the workspace's current records in pages.
3. Call `grant_workspace_permissions` separately with the same workspace and
   target, the agreed `scopes`, the observed `expected_revision` (zero for a
   first grant) and a new request key. The target must already be known to the
   installation. Compare the resulting scopes and revision with a fresh
   permission inspection.
4. Reconnect as the authorized target and call `get_workspace` with the exact
   ID from creation. A reader can now inspect that workspace.
5. To withdraw access, call `revoke_workspace_permissions` with the exact
   workspace, target, scopes to remove, current revision and a distinct request
   key. Inspect the resulting scopes separately. Reuse the owner's cursor,
   unchanged and with the same query, to page through
   `list_workspace_permission_history`.

After an interrupted permission change, use the target's history to match the
workspace, actor, target, operation, scopes, prior revision and command key.
Current access alone cannot identify which request changed it. A lost creation
reply may leave attribution unknown even when the workspace is readable.
Stop on an ambiguous result. Further work, including a new submission, needs
its own decision. This workflow operates on existing identities. The
authentication provider retains responsibility for issuing their credentials.
