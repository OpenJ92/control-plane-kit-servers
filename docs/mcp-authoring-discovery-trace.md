# MCP authoring and discovery source trace — #417

Source/design draft, November 14, 2026. Governing issues: Servers #417 under
#396, with #404 inspection, #408 authoring and #413 guidance. No implementation,
application tests, installation access, credentials, provider calls or topology
write occurred. This is independent of #399's actual installed-read acceptance.

The trace uses accepted Servers #402 merge
`0610e9454dd9a75a6e6bf5e89fe281c8631cccaa`, G Core
`f56bb5c4cfde76764d39c5377d4270c5b23c3ba1` and G Operations
`70154b6698e101159326b08646f2dba90dda87cd`, with the selected G cohort from
products/cpk_server/grandparent-cohort.json. The existing standard profile and
the explicitly restricted grandparent profile are separate. A later sibling's
actual source/profile/witness must be named by its owner; these source facts
are not a claim about that installation's exposed tools or records.

## First findings

1. Product list/detail HTTP owners already exist, but neither MCP profile
   exposes them. They are the smallest first discovery connection in #404.
   More instructions alone cannot supply the workspace's registered products.
2. Product detail does expose connectivity and configuration *shapes*, but is
   explicitly a noncanonical display. It cannot be decoded as a canonical
   product document or used as the inverse of a redacted projection. Core
   instantiation requires a real canonical product/document and explicit
   ProductInstanceConfiguration. The currently traced public command accepts
   a compiled graph, not a recipe of registered references and instance inputs.
3. Session-start and first-save have different durable idempotency coordinates.
   Both owners support exact replay, but neither has a public read-only lookup
   by that coordinate. Known saved revision readback works; an entirely lost
   reply cannot generally be resolved by choosing a latest session/draft/action.

## Instructions, schemas and public workspace data

Servers mcp_adapter.py:28 _READS, :62 _input_schema, :96 StandardMcpAdapter and
:131 SDK Server instructions are the existing owners of MCP discovery framing.
The standard profile currently advertises18 reads and one saved-revision
preparation command. The G profile permits workspace, Desired, exact revision
and its attempts only; direct command calls cannot bypass that restriction.
Neither profile advertises product list/detail or draft create/revise/select.

| Source of knowledge | What belongs there | What must not be inferred |
| --- | --- | --- |
| SDK instructions / concise tool descriptions (#413) | Stable vocabulary: workspace, registered immutable ProductReference, provider versus requirement socket, explicit instance inputs, saved draft/revision, redacted readback; proposal versus authorized save versus Desired selection; which tool obtains current facts. | Current products, versions, sockets, grants, admission or readiness cannot be hard-coded into instructions. Labels/descriptions are data, never instructions granting authority. |
| Tool input/output schemas (#404/#408) | Typed bounded coordinates, pagination, public authoring input shape, required concurrency/lifecycle fields, safe success/error/unknown meaning. | A generic graph object with no documented grammar is not an adequate construction guide. Schemas do not grant access or invent an owner. |
| Authorized workspace products (#404) | Current active directory, exact reference/digest, image selection and public contract projection from the registered-product owner. Follow returned cursor, then read selected exact details. | Installed availability, authorized use, complete canonical descriptor contents and a compatible graph are not implied by a product name or list entry. |
| Other current public observations (#404/#413) | Required runtime/admission/material-reference context and current workspace/Desired fences, only through their own authorized tools. | Denied is not absent; stored health is not fresh; no new runtime or material is allocated just to author a proposal. |
| Operator-private input | Protected material/reference setup or credential custody through its reviewed owner. Ordinary public configuration choices may be supplied explicitly in authoring input. | No secret values, protected configuration content, private descriptor reconstruction or implicit key generation in a model tool. |

## Exact HTTP and owner path

All paths below are declared by G Core operations/http.py and mounted by
Servers http_host.install_operator_http_routes. boundary._decode_http_payload
and _decode_http_read_query own HTTP framing; the awaited shared application
owns dispatch. Operations CpkServerOperationsApplication._prepare resolves
current workspace authority; _trusted_context applies the existing route policy.
There is no internal HTTP round trip required for a future MCP adapter.

| Operation | Existing HTTP path | Actual G701 owner / law |
| --- | --- | --- |
| Directory | GET /workspaces/{workspace_id}/products | CpkServerReadService.handle, _read_page_request_for_route → _read_model → InstanceReadService.products → _ProductDirectoryReadProjection.page; INSTANCE_WORKSPACE_READ before store acquisition. Bounded scoped pagination. |
| Exact product | GET /workspaces/{workspace_id}/products/{descriptor_sha256} | Same read service; validate ProductDescriptorDigest → InstanceReadService.product_detail → directory_detail on the registered-product store. Active/workspace-specific record; safe noncanonical display. |
| Session start | POST /workspaces/{workspace_id}/sessions | CpkServerLifecycleService.handle:1561 builds StartOperationSession from current actor, title, key and metadata → OperationCommandService.start_in_unit_of_work. Workspace edit; no graph or runtime action. |
| Save | POST /workspaces/{workspace_id}/desired-topology-drafts | CpkServerPlanningService.handle:875 decodes graph with DEFAULT_GRAPH_CODEC and builds CreateDesiredTopologyDraft(context, session_id, graph, title, idempotency_key, receiver_lifecycle) → DesiredTopologyDraftCommandService.execute. |
| Revise | POST /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/revisions | Same owner, with exact draft_id and expected_head_revision. Does not silently rebase or mutate a prior revision. |
| Exact saved read | GET /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/revisions/{revision} | CpkServerReadService → InstanceReadService.desired_topology_draft_revision → _DesiredTopologyDraftReadProjection.detail; immutable draft/revision/graph identity plus validated redacted graph projection. |
| Attempts | GET /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/revisions/{revision}/attempts | Revision-history owner, scoped cursor and permission. A saved-only revision may correctly have no attempts; save is not execution. |
| Select Desired | POST /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/select | CpkServerPlanningService.handle:851 → SelectDesiredTopologyDraft → _execute_reference_command; exact revision, current Desired authored/projection/generation fence and receiver expectation. Independent authorized mutation, never implicit save behavior. |
| Verify Desired | GET /workspaces/{workspace_id}/graphs/desired | Existing workspace-graph public projection; compare selected immutable identity and generation, not original source bytes against redacted JSON. |
| Known-session actions | GET /workspaces/{workspace_id}/sessions/{session_id}/actions | Operations history projection; bounded safe actions, but no public lookup by command idempotency key. It does not resolve every unknown outcome. |

Directory and draft/session reads require current caller authority on every
request; commands need their existing workspace-edit/owner policy. The G4
profile intentionally excludes most of this workflow. #404/#408 must qualify an
explicit supported exposure choice rather than weakening #399's four-read
restriction or silently selecting a different dependency cohort.

## What product detail actually supplies

G701 read_services/product_directory.py:84 _contract returns:

- provider socket names/protocols and provider ports;
- requirement names/protocols, env_names, required flag and binding kind;
- configuration artifact slot ID/path/media type/mode;
- public environment *names*, material delivery shapes and retained mount IDs/paths;
- capabilities, lifecycle, verification check shapes and control-surface shapes.

detail:146 keeps the immutable ProductReference and selected image, with
projection_kind=noncanonical-product-display. It deliberately omits canonical
descriptor bytes, arbitrary registration/provenance metadata, public environment
values, configuration content and actual material/reference handles. Its source
field is evidence of registration origin, not authority to fetch arbitrary URLs.
ProductDirectoryBoundaryTests and ProductDirectoryStoreTests in
test_product_directory.py cover denial before hostile cursor/UoW, scoped
pagination,201 records across maximum pages, redaction, slot shapes, current
revocation, cross-workspace refusal and authorized-empty versus missing admission.

This is useful discovery data. It does not specify all semantic choices inside
an arbitrary product's JSON configuration, or make the display round-trip to a
canonical product. Ask for missing meaningful choices; do not invent defaults.

## Two registered products and one compatible edge

This is a source-level trace, not an executed graph or a promise that any two
particular products exist in the live workspace.

Public proposal inputs: exact reference/digest for product P and C, two distinct
role IDs, the chosen existing runtime context, explicit instance configuration
values/references, and one provider/requirement pair. For example P's `http`
provider and C's `upstream` requirement must both declare HTTP, with compatible
binding; other required inputs/sockets must also be satisfied. Merely sharing
an endpoint name is insufficient. No runtime allocation occurs in a value.

The existing owner-supported in-process construction is:

```text
(workspace, pinned ProductReference P/C)
  -> registered_products.get(workspace, exact reference), require active
  -> original RegisteredProduct.descriptor_document P/C
  -> Core instantiate_product(product, role_id, ProductInstanceConfiguration)
  -> two ordinary ApplicationBlocks
  + SocketConnection(provider_role, provider_socket,
                     consumer_role, requirement_socket, protocol, edge_id)
  -> DeploymentTopology(explicit RuntimeContext(children=...))
  -> compile_topology -> validate_graph -> DEFAULT_GRAPH_CODEC descriptor
```

Core products.py:1523 instantiate_product, :1536 instantiate_catalog_product and
:1550 _instantiate_document consume the real product document; ProductInstance-
Configuration:1375 carries explicit public bindings/artifacts/material references.
The exact contract slot keys are checked by _validate_instance_configuration:2146.
The pure materializer/compilation retains node product_identity,
product_descriptor_digest and selected OCI image. Core algebra.SocketConnection
and the existing graph validator own edge/protocol/binding/environment laws.
No process, Docker or provider interpreter is invoked by those pure operations.

The registered-product store has the original documents, but the public
directory and GraphAuthoringService.selectable_products expose references and
display data only. In this source, no Operations public operation combines
registered-reference resolution with Core instance construction. The HTTP save
decoder instead expects a complete compiled graph. Looking up its product
metadata during save validates workspace membership/status and material laws;
it is not an inverse display→canonical-product constructor.

**Smallest missing bridge for review:** a bounded owner-supported public
authoring input contract for exact registered references + explicit instance
inputs + typed connections, reusing that Core construction and the current
registered-product/draft owners. Canonical documents should stay owner-side.
Its inspectable public proposal/save readback must preserve identity without
leaking canonical private-capable contents. Choose the owner/API boundary before
implementation; this draft invents no route, new durable proposal store or
alternate planner. A client that independently holds an approved canonical
document can already use Core, but that is an additional input, not completion
from the promised directory projections alone.

Authorize before owner-side acquisition, resolve by the complete reference
including descriptor digest (not identity/name alone), and refuse foreign or
revoked records. No arbitrary remote catalogue fetch or canonical-value export
is implied. The pure proposal's required authority and its safe output versus
the authorized save input must be decided with the owning contract; the MCP
adapter must not invent those semantics.

For the first walkthrough, choose a small compatible pair requiring only
explicit supported public inputs, without missing protected material or new
receiver/key generation. Runtime/permission/material prerequisites still need
their named current owners. Public discovery must not pretend an incompatible
HTTP-provider/PostgreSQL-requirement pair is an example of a valid edge.

## Lost replies: two independent correlations

### Session-start reply lost, no session ID known

Before dispatch the caller knows workspace, authenticated actor, full start
intent and K_start. G701 workflows.py:219 locks (workspace_id,K_start), looks up
session_for_idempotency, compares the complete intent fingerprint and returns
the original session/action on exact replay. A different intent under the key
conflicts. Concurrent identical starts converge. This is real owner support,
not MCP transport-ID semantics.

Public list/detail session descriptors in read_services/operations_history.py:287
omit idempotency key/fingerprint. There is no canonical read route accepting
(workspace,K_start) to return that exact outcome before knowing session_id.
Scanning open sessions by newest/title/metadata is not an authoritative exact
lookup and misses a subsequently closed session. Caller-chosen metadata does
not create a unique lookup contract.

An exact owner replay can recover the original ID if committed, but can create
the session if the first call never committed. It remains a command, requiring
current authority and an explicit supported recovery disposition. It is not a
read-only outcome query, automatic retry permission or proof of rollback.

### First-save reply lost, session known but no draft ID known

Before dispatch the caller knows session_id, exact graph/title/receiver intent,
current authority context and K_save. DesiredTopologyDraftCommandService:204
locks (session_id,K_save), checks the full intent fingerprint and returns the
original draft_id/revision/graph_id on exact replay before new allocations and
fresh session/product/head admission. Changed intent conflicts. Current public
authorization still applies before entering the owner; historical replay does
not confer revoked workspace authority.

The private store action_for_idempotency is exact, but the public action
projection (:300) omits key/fingerprint. Known draft/revision can be read safely;
the safe action payload may contain saved coordinates. Without an authoritative
correlation to K_save, listing session actions/drafts and selecting the latest
does not resolve a general entirely lost first-save response. A single-owned-
session fixture is not a general concurrent outcome lookup guarantee.

The existing HTTP client persists its private request journal and explicitly
replays exact requests on resume. That proves a supported client mechanism,
not an available public MCP outcome endpoint. Do not transplant that journal or
its retry state machine. #408 needs a reviewed public owner outcome contract
for each correlation stage, or an explicit exact-replay restriction/authorization
with truthful committed/not-known meaning. No replay was performed here.

## Governing laws before implementation

| Source test / classification | Law to preserve or new boundary to prove |
| --- | --- |
| G Operations test_product_directory.py:55/64/73/101/112/147/161/185/193/199; isomorphic | Current permission before hostile input/UoW, digest/cursor/limit validation, scoped paginated list and HTTP/MCP owner parity, exact pinned identity and redacted contract shape, current active status and empty-versus-unadmitted distinction. Existing direct MCP-shaped tests are not SDK discovery or installed evidence. |
| Core test_product_instantiation.py:87/118/131/148; isomorphic | Canonical catalogue product instantiates and codec round-trips with retained identity; missing/extra slot keys refuse; explicit configuration values may vary without changing product contract. |
| Core test_graph_validation.py:75/84/108/186/216/248; isomorphic | Validation is pure; missing required sockets, incompatible endpoints, duplicate/multiple edges, mismatched binding/environment assignments and invalid verification targets fail. |
| G Operations test_desired_topology_drafts.py:27/82/113/344/378; isomorphic | Save returns exact draft/revision/graph, revisions stay independent, runtime truth unchanged, invalid graph/foreign/revoked product refuse; exact replay precedes allocation/fresh admission, changed intent conflicts; scoped pagination/readback never crosses workspace. |
| G Operations test_workflows.py:114/132; isomorphic | Session-start replay compares the full fingerprint; changed intent conflicts and concurrent identical requests converge on one session/action. |
| Servers test_topology_client_catalogue.py:260/288/299/318/338; reference only | Existing client preserves opaque graph, explicit selection/fences and exact private-journal resume. These scripted replies are not durable owner proof or a general public outcome lookup. Selection response-loss test is not an executed lost first-create witness. |
| Servers test_standard_mcp.py, test_grandparent_mcp.py, test_revision_history_composition.py; isomorphic + new SDK exposure | Preserve real client discovery/auth/bounds/profile refusal and HTTP-equivalent redacted revision/history. Add real SDK calls for the newly exposed product/authoring families, with the selected cohort, not only recording adapters. |
| New #408 reference-to-instance bridge; new-law after owner design | Two exact active product references + explicit inputs + compatible edge yield a valid graph with unchanged pins; reject foreign/revoked/mismatched reference, missing/extra input, incompatible edge and private projection leakage before persistence. Name the actual owner interface and typed tests before implementing the adapter. |
| New public loss-correlation contracts, if chosen; new-law after owner design | Separate exact lookup for unknown session ID and unknown first draft ID, current caller/workspace/actor binding, changed-key/intent mismatch, concurrent intents, nonrecorded versus denied/unavailable/unknown, no secret/graph-body leakage. No newest-record heuristic or automatic resubmission. |

## Handoff and next source slices

1. #404 exposes existing authorized product list/detail with correct page schema;
   #413 adds concise stable guidance that points to those live records and
   treats descriptions as untrusted data. Preserve the G4 profile's boundary.
2. Resolve the owner boundary for public pinned-reference instance authoring;
   directory projection is not canonical input. Resolve the two independent
   lost-reply correlation dispositions before promising the full walkthrough.
3. #408 maps typed save/revise and independent select commands to existing
   session/draft/receiver owners, then exact revision/attempt/Desired readback.
   Plan preparation, human website approval and execution remain later steps.
4. After source reviews/cohort qualification, a separately reviewed installed
   action proves the walkthrough on the named sibling. #399's known-revision
   seed/read evidence remains its own work; the historical #163 graph belongs
   to another installation. No live write or source example closes it.

Security/data/history: only source and issue documents were read. Canonical
product values are not exposed by this draft; proposals do not mutate Desired.
Existing owner transactions, action records, exact graph identities and safe
projections remain authoritative. There is no new auth policy, retry engine,
credential access, session/draft allocation, runtime or network exposure.
This document is non-executable-scaffold. Whitespace/source-reference checks
are its validation; no artificial prose test or application PASS is claimed.

Pinned sources for review:
[Servers MCP adapter](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/src/control_plane_kit_servers_cpk_server/mcp_adapter.py),
[G701 product directory](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/src/control_plane_kit_operations/read_services/product_directory.py),
[G701 draft owner](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/src/control_plane_kit_operations/desired_topology_drafts.py),
[G701 session owner](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/src/control_plane_kit_operations/workflows.py),
[G701 public history projection](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/src/control_plane_kit_operations/read_services/operations_history.py),
[Core product instantiation](https://github.com/OpenJ92/control-plane-kit/blob/f56bb5c4cfde76764d39c5377d4270c5b23c3ba1/control-plane-kit-core/src/control_plane_kit_core/products.py).
