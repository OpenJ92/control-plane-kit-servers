# Standard MCP operator connection

Design checkpoint for Servers #396; implementation and executable evidence are
pending. Accepted base: `2093f5182748a4aca638f362eece0bc4f063a1db`,
`roadmap/1813-runtime-control`, accepted in PR #395 comment 6840942585.
The isolated branch is `codex/396-standard-mcp`.

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

## Proposed composition

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
stateless HTTP; enter the SDK manager from the host lifespan.

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
or #391 restart is included. No executable validation has run at this checkpoint.

Official references: [SDK ASGI integration](https://py.sdk.modelcontextprotocol.io/run/asgi/),
[SDK protocol versions](https://py.sdk.modelcontextprotocol.io/protocol-versions/),
[Codex MCP setup](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
