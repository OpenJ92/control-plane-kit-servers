# MCP operator coverage — Servers #403 / parent #396

Draft for review, November 14, 2026. **Offline specification only.** No runtime,
installation, credential, client configuration or provider access was performed.
Acceptance remains ordered after #399's installed four-read milestone. This
matrix does not close #403 or #396, expose a tool, or authorize an effect.

## Exact sources and evidence levels

This documentation branch starts at accepted Servers merge
`0610e9454dd9a75a6e6bf5e89fe281c8631cccaa` (#402). The source anchor **S** below
means that immutable revision, including StandardMcpAdapter and the real shared
OperationsApplicationFactory. The #399 packaging snapshot
`c15813f89624348dc958f94919504d4a77748ee4` has no changes to that product Python
source or grandparent-cohort.json; later maintenance source is not silently
substituted for the accepted application. Reconcile a successor's actual source
and effective profile before using this draft for installed acceptance.

| Cohort | Immutable dependency selection | Meaning here |
| --- | --- | --- |
| **G** selected grandparent | Core `f56bb5c4cfde76764d39c5377d4270c5b23c3ba1`; Operations `70154b6698e101159326b08646f2dba90dda87cd`; Interpreters `e438f6e522ad0a23a7acef460be08690f48b2e17`; SDK `d61b374cb2a23d773c31748f47f88169499298b7`; MCP `2.3.0` | Explicit `grandparent-read-only-v1`; four allowed read tools. Retained Interpreters module tree `97507ed009a5e5c8aa81d280288a2f81ce807835`; no Secrets distribution in this server cohort. |
| **D** default source | Core `7afef43f3d3b981094e37dcb3062b6e3a4f3d674`; Operations `885513e348b5b9cdb077c9f8804e98d9b2c0e803`; Interpreters `685c86279ae50ac16128d9417429f97db9af982a`; SDK `220f63169e4bac79653937e97727406255279f7b`; Secrets `09442303740ed2e648cf354e35dd61df93974b9c` | Explicit `standard`; 18 curated reads plus saved-revision prepare. Default saved planning is not the G701 managed-readiness contract. |
| Installed installation | Not inferred from either checkout | #399's retained observation established the historical service still used its historical image and had no MCP profile. It did not establish a desktop connection. All installed MCP witnesses in this matrix are **PENDING**; source/isolated results are separate. |

Sources reused, rather than a new operation registry:

- **H**: [G Core operations/http.py](https://github.com/OpenJ92/control-plane-kit/blob/f56bb5c4cfde76764d39c5377d4270c5b23c3ba1/control-plane-kit-core/src/control_plane_kit_core/operations/http.py), `operator_read_http_routes` and `operator_command_http_routes`. `H:n` in a row is its exact tuple line.
- **P**: [G Core operations/parity.py](https://github.com/OpenJ92/control-plane-kit/blob/f56bb5c4cfde76764d39c5377d4270c5b23c3ba1/control-plane-kit-core/src/control_plane_kit_core/operations/parity.py), `_OPERATOR_READ_PROJECTIONS`, `_OPERATOR_COMMANDS`, `HTTP_ONLY_COMMAND_ROUTE_IDS`. A parity name is a declaration, not SDK discovery.
- **O**: [G Operations cpk_server.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/src/control_plane_kit_operations/cpk_server.py), actual services, typed request construction and route authorization. Row authority/owner details below are **G701**, not a claim of independently checked D885 behavioral equivalence.
- **S**: [Servers source tree](https://github.com/OpenJ92/control-plane-kit-servers/tree/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server). HTTP: `http_host.py:16 install_operator_http_routes` → `boundary.py:106 CpkServerHttpBoundary`, `:383 _decode_http_payload`, `:411 _decode_http_read_query` → authenticated application. Standard MCP: `mcp_adapter.py:96 StandardMcpAdapter`, `:62 _input_schema`, `:152 call_tool` → the same awaited dispatcher; no internal HTTP hop.
- **T**: [PublicHttpTransport.call](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py#L65). The table names a public `TopologyClient` method where there is a concrete workflow reference; generic T.call means route transport exists, not that a dedicated safe workflow or MCP method exists. `TopologyClient.apply` currently contains an optional approval path: reference its owner sequencing, **do not port self-approval into an ordinary agent**.

### Inventory reconciliation

Static source extraction found **102 G HTTP route IDs: 53 reads + 49 commands**.
Every unique route literal in H is represented once below; no additional row or
omitted literal. P has **53 projection bindings + 48 command bindings**: the
one difference is deliberately HTTP-only `command.secret-material.provision`.
D has 101 corresponding HTTP routes: G's `read.workspaces` is absent from the
selected D Core. Do not infer its availability from a newer/default checkout.

The standard SDK adapter advertises **18 reads + 1 prepare command**. G's
profile admits exactly **4 reads** and refuses every command even if a client
omits its allowlist. The older framework-neutral MCP boundary's broader Core
parity dispatch remains legacy source; it does not establish standard SDK or
installed exposure. Do not remove a profile/filter to claim coverage.

All HTTP entries below mean **declared and mounted from the selected inventory**;
a successful operational response additionally needs the current principal,
configured owner/ports, admitted authority and supported cohort. A 403 is a
denial, a 501 unsupported owner, and a 503 unavailable owner/outcome; none proves
absence of a resource or successful work. The installed witness for **every row**
is PENDING under #399/#414. The common witness column is stated here to avoid
102 repetitions; even the four G rows have no installed-client PASS here.

## Reading the maintained matrix

Disposition: **EX** exposed in standard source; **MA** missing standard adapter;
**MO** missing usable selected owner contract; **DR** deliberate restriction;
**EB** external bootstrap prerequisite (workflow rows below). These dispositions
are proposals for North/Meridian review, not accepted completion labels. A row
can have an adapter gap and a separately named owner prerequisite.

`std` gives the actual standard tool name if exposed, otherwise the *declared*
Core parity name with **not exposed**. `G4` means allowed by the G profile;
`G restricted` means intentionally omitted by that initial profile, in addition
to the standard disposition. All reads use the closed MCP `_input_schema`:
path coordinates, plus only the explicitly admitted pagination/extra fields.
G4 schemas are the same source schema for those four operations. Unexposed rows
have **no standard SDK input schema**, regardless of a Core request schema.
The prepare schema is separately documented below.

Authority cells name G `PolicyScope` enum members (not coarse HTTP auth labels).
All ordinary policies also restrict principal kind to operator; worker rows
explicitly permit worker/service and require EXECUTION_OPERATE. WA and PP use
their own independent installation/provider administration policies; do not
replace them with workspace-edit. Core approval labels: **N** not-required,
**S** submits-for-approval, **D** decides-approval, **C** requires-current-approval.
These are declared parity laws to compare against the owner; N is not human
consent for an agent's consequential administration. G1 records that gap.

Owner/decoder keys resolve to O: **R** CpkServerReadService:693 (typed read/page
queries and InstanceReadService), **P** CpkServerPlanningService:821,
**A** CpkServerApprovalService:1489 → ApprovalCommandService,
**D** CpkServerAdmissionService:1525 → ExecutionAdmissionCommandService,
**L** CpkServerLifecycleService:1549 → operation/run/advancement owners,
**E** CpkServerExecutionService:1674 → ExecutionCoordinator or the separate
DelegationKeyGeneration/SecretMaterialProvision owners,
**G** CpkServerGatewayProbeService:1807 → GatewayProbeCommandService,
**WA** CpkServerWorkspaceAdministrationService:1972,
**PP** CpkServerProviderPolicyAdministrationService:2304,
**U** CpkServerUnsupportedService:2419. HTTP query/body decoding is shared H/S
transport work; these owner decoders construct the actual typed domain command.

`O/test_file.py:n` or `S/test_file.py:n` identifies an existing **source test
reference**, not a fresh execution or an automatic success proof for the row.
Some are negative/transport cases. Rows explicitly marked **test evidence gap**
have no literal route-specific reference in the reused searches; inventory laws
alone cannot prove their successful owner behavior. Before implementation,
inspect that row's named tests, extract preserved negative/positive laws and add
only meaningful missing behavior tests. No tests were run for this prose draft.

## Read operations

| Canonical route / H line | HTTP path; request → response | G owner/decoder; HTTP client reference | G authority; effect | Standard schema/exposure; G profile | Existing test source reference | Draft disposition / next issue |
| --- | --- | --- | --- | --- | --- | --- |
| `read.workspaces` (G only; D absent; H:309) | `GET /workspaces`<br>WorkspaceInventoryReadRequest → WorkspaceInventoryPage | R/_inventory_arguments<br>T.call (route transport) | inventory operator/current inventory policy; read | `list_workspaces` **not exposed**; G restricted | O/test_cpk_server_adapters.py:929; O/test_postgres_workspace_inventory.py:256 | MA; #404 |
| `read.workspace` (H:310) | `GET /workspaces/{workspace_id}`<br>EmptyRequest → WorkspaceReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_workspace` std read schema; **G4** | O/test_cpk_server_adapters.py:979; O/test_cpk_server_adapters.py:1190 | EX (standard source); #404 |
| `read.receiver-authoring-context` (H:315) | `GET /workspaces/{workspace_id}/receiver-authoring-context`<br>ReceiverAuthoringContextReadRequest → ReceiverAuthoringContextReadResponse | R/ReceiverAuthoringContextQuery<br>T.call (route transport) | INSTANCE_WORKSPACE_READ + DELEGATION_KEY_READ; read | `get_receiver_authoring_context` **not exposed**; G restricted | O/test_managed_selected_update_execution.py:70 | MA; #404 |
| `read.current-graph` (H:320) | `GET /workspaces/{workspace_id}/graphs/current`<br>EmptyRequest → GraphReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_current_graph` std read schema; G restricted | O/test_cpk_server_adapters.py:1171; O/test_cpk_server_adapters.py:2712 | EX (standard source); #404 |
| `read.desired-graph` (H:325) | `GET /workspaces/{workspace_id}/graphs/desired`<br>EmptyRequest → GraphReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_desired_graph` std read schema; **G4** | O/test_receiver_authoring_context.py:69 | EX (standard source); #404 |
| `read.desired-topology-drafts` (H:330) | `GET /workspaces/{workspace_id}/desired-topology-drafts`<br>EmptyRequest → DesiredTopologyDraftsReadResponse | R/_closed_read_arguments + _read_model<br>TopologyClient.draft_list | INSTANCE_WORKSPACE_READ; read | `list_desired_topology_drafts` std read schema; G restricted | O/test_desired_topology_drafts.py:362; O/test_desired_topology_drafts.py:363 | EX (standard source); #404 |
| `read.desired-topology-draft-revisions` (H:335) | `GET /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/revisions`<br>EmptyRequest → DesiredTopologyDraftRevisionsReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_desired_topology_draft_revisions` std read schema; G restricted | O/test_desired_topology_drafts.py:45; O/test_desired_topology_drafts.py:209 | EX (standard source); #404 |
| `read.desired-topology-draft-revision` (H:340) | `GET /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/revisions/{revision}`<br>EmptyRequest → DesiredTopologyDraftRevisionReadResponse | R/_closed_read_arguments + _read_model<br>TopologyClient.draft_show | INSTANCE_WORKSPACE_READ; read | `get_desired_topology_draft_revision` std read schema; **G4** | O/test_desired_topology_drafts.py:48; O/test_desired_topology_drafts.py:268 | EX (standard source); #404 |
| `read.desired-topology-draft-revision-preparations` (H:345) | `GET /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/revisions/{revision}/preparations`<br>EmptyRequest → DesiredTopologyDraftRevisionPreparationsReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_desired_topology_draft_revision_preparations` std read schema; G restricted | O/test_read_pages.py:218 | EX (standard source); #404 |
| `read.desired-topology-draft-revision-attempts` (H:350) | `GET /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/revisions/{revision}/attempts`<br>EmptyRequest → DesiredTopologyDraftRevisionAttemptsReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_desired_topology_draft_revision_attempts` std read schema; **G4** | O/test_read_pages.py:219 | EX (standard source); #404 |
| `read.operator-overview` (H:355) | `GET /workspaces/{workspace_id}/overview`<br>EmptyRequest → OperatorOverviewReadResponse | R/_closed_read_arguments + _read_model<br>TopologyClient.overview | INSTANCE_WORKSPACE_READ; read | `get_operator_overview` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1003; O/test_cpk_server_adapters.py:1022 | MA; #404 |
| `read.operator-graph` (H:360) | `GET /workspaces/{workspace_id}/operator-graph`<br>EmptyRequest → OperatorGraphReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_operator_graph` **not exposed**; G restricted | Core HTTP inventory; **test evidence gap** | MA; #404 |
| `read.activity` (H:365) | `GET /workspaces/{workspace_id}/activity`<br>EmptyRequest → ActivityTimelineReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_activity_timeline` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1268; O/test_cpk_server_adapters.py:1356 | MA; #404 |
| `read.sessions` (H:370) | `GET /workspaces/{workspace_id}/sessions`<br>EmptyRequest → OpenSessionsReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_open_sessions` std read schema; G restricted | O/test_cpk_server_adapters.py:1269; O/test_cpk_server_adapters.py:1357 | EX (standard source); #404 |
| `read.session-detail` (H:375) | `GET /workspaces/{workspace_id}/sessions/{session_id}`<br>EmptyRequest → SessionDetailReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_session_detail` std read schema; G restricted | O/test_cpk_server_adapters.py:1375 | EX (standard source); #404 |
| `read.session-actions` (H:380) | `GET /workspaces/{workspace_id}/sessions/{session_id}/actions`<br>EmptyRequest → SessionActionsReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_session_actions` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1207; O/test_cpk_server_adapters.py:1219 | MA; #404 |
| `read.session-plans` (H:385) | `GET /workspaces/{workspace_id}/sessions/{session_id}/plans`<br>EmptyRequest → SessionPlansReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_session_plans` std read schema; G restricted | O/test_cpk_server_adapters.py:1270; O/test_cpk_server_adapters.py:1359 | EX (standard source); #404 |
| `read.session-approvals` (H:390) | `GET /workspaces/{workspace_id}/sessions/{session_id}/approvals`<br>EmptyRequest → SessionApprovalsReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_session_approvals` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1272; O/test_cpk_server_adapters.py:1364 | MA; #410 |
| `read.plan-detail` (H:395) | `GET /workspaces/{workspace_id}/plans/{plan_id}`<br>EmptyRequest → PlanDetailReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_plan_detail` std read schema; G restricted | O/test_cpk_server_adapters.py:1380; O/test_cpk_server_adapters.py:2528 | EX (standard source); #404 |
| `read.plan-runs` (H:400) | `GET /workspaces/{workspace_id}/plans/{plan_id}/runs`<br>EmptyRequest → PlanRunsReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_plan_runs` std read schema; G restricted | O/test_cpk_server_adapters.py:1277; O/test_cpk_server_adapters.py:1370 | EX (standard source); #404 |
| `read.run-events` (H:405) | `GET /workspaces/{workspace_id}/runs/{run_id}/events`<br>EmptyRequest → RunEventsReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_run_events` std read schema; G restricted | O/test_cpk_server_adapters.py:410; O/test_cpk_server_adapters.py:415 | EX (standard source); #404 |
| `read.approval-detail` (H:410) | `GET /workspaces/{workspace_id}/approvals/{approval_id}`<br>EmptyRequest → ApprovalDetailReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_approval_detail` std read schema; G restricted | O/test_cpk_server_adapters.py:1385; O/test_cpk_server_adapters.py:2289 | EX (standard source); #410 |
| `read.delegation-keys` (H:415) | `GET /workspaces/{workspace_id}/delegation-keys`<br>EmptyRequest → DelegationSigningKeyCollectionReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | DELEGATION_KEY_READ; read | `list_delegation_keys` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3615; O/test_cpk_server_adapters.py:3629 | MA; #407 |
| `read.delegation-key-generation` (H:420) | `GET /workspaces/{workspace_id}/delegation-key-generations/{request_id}`<br>EmptyRequest → GeneratedDelegationKeyReceipt | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ + DELEGATION_KEY_READ; read | `get_delegation_key_generation` **not exposed**; G restricted | O/test_delegation_key_generation_commands.py:468; O/test_delegation_key_generation_commands.py:495 | MA; #407 |
| `read.secret-material-provision` (H:425) | `GET /workspaces/{workspace_id}/secret-material-provisions/{request_id}`<br>EmptyRequest → ProvisionedSecretMaterialReceipt | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ + SECRET_PROVIDER_READ; read | `get_secret_material_provision` **not exposed**; G restricted | O/test_secret_material_provision_commands.py:366; O/test_secret_material_provision_commands.py:367 | MA; #407 |
| `read.gateway-verifier-configuration` (H:430) | `GET /workspaces/{workspace_id}/gateways/{gateway_node_id}/verifier-configuration`<br>EmptyRequest → GatewayVerifierConfigurationReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | DELEGATION_KEY_READ; read | `get_gateway_verifier_configuration` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3644 | MA; #404 |
| `read.workload-verifier-configuration` (H:435) | `GET /workspaces/{workspace_id}/workload-verifier-configuration/{purposes}`<br>EmptyRequest → WorkloadVerifierConfigurationReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | DELEGATION_KEY_READ; read | `get_workload_verifier_configuration` **not exposed**; G restricted | O/test_workload_verifier_configuration.py:35 | MA; #404 |
| `read.pending-approvals` (H:440) | `GET /workspaces/{workspace_id}/approvals/pending`<br>EmptyRequest → PendingApprovalsReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_pending_approvals` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1276; O/test_cpk_server_adapters.py:1368 | MA; #410 |
| `read.observed-state` (H:445) | `GET /workspaces/{workspace_id}/observed-state`<br>EmptyRequest → ObservedStateReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_observed_state` **not exposed**; G restricted | O/test_cpk_server_adapters.py:782; O/test_current_metadata_read_pages.py:116 | MA; #404 |
| `read.ingress-authorities` (H:450) | `GET /workspaces/{workspace_id}/ingress-authorities`<br>EmptyRequest → IngressAuthorityCollectionReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INGRESS_AUTHORITY_READ; read | `list_ingress_authorities` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1782; O/test_cpk_server_adapters.py:1796 | MA; #404 |
| `read.ingress-authority-detail` (H:455) | `GET /workspaces/{workspace_id}/ingress-authorities/{authority_ref}`<br>EmptyRequest → IngressAuthorityDetailReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INGRESS_AUTHORITY_READ; read | `get_ingress_authority_detail` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1805 | MA; #404 |
| `read.gateway-probe-timeline` (H:460) | `GET /workspaces/{workspace_id}/gateway-probes`<br>EmptyRequest → GatewayProbeTimelineReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_gateway_probes` **not exposed**; G restricted | O/test_gateway_probe_read_pages.py:343; O/test_large_read_route_parity.py:258 | MA; #404 |
| `read.gateway-probe-detail` (H:465) | `GET /workspaces/{workspace_id}/gateway-probes/{probe_id}`<br>EmptyRequest → GatewayProbeDetailReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_gateway_probe_detail` **not exposed**; G restricted | O/test_gateway_probe_read_pages.py:435 | MA; #404 |
| `read.control-surface` (H:470) | `GET /workspaces/{workspace_id}/control-surface`<br>EmptyRequest → ControlSurfaceReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_control_surface` **not exposed**; G restricted | Core HTTP inventory; **test evidence gap** | MA; #404 |
| `read.runtime-authorities` (H:475) | `GET /workspaces/{workspace_id}/runtime-authorities`<br>EmptyRequest → RuntimeAuthorityCollectionReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | RUNTIME_AUTHORITY_READ; read | `list_runtime_authorities` **not exposed**; G restricted | O/test_cpk_server_adapters.py:2961; O/test_cpk_server_adapters.py:2976 | MA; #404 |
| `read.runtime-authority-detail` (H:480) | `GET /workspaces/{workspace_id}/runtime-authorities/{authority_ref}`<br>EmptyRequest → RuntimeAuthorityDetailReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | RUNTIME_AUTHORITY_READ; read | `get_runtime_authority_detail` **not exposed**; G restricted | O/test_cpk_server_adapters.py:2988 | MA; #404 |
| `read.runtime-authority-deliveries` (H:485) | `GET /workspaces/{workspace_id}/runtime-authority-deliveries`<br>EmptyRequest → RuntimeAuthorityDeliveryCollectionReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | RUNTIME_AUTHORITY_DELIVERY_READ; read | `list_runtime_authority_deliveries` std read schema; G restricted | O/test_cpk_server_adapters.py:3074; O/test_current_metadata_read_pages.py:118 | EX (standard source); #404 |
| `read.runtime-authority-delivery-detail` (H:490) | `GET /workspaces/{workspace_id}/runtime-authority-deliveries/{authority_ref}`<br>EmptyRequest → RuntimeAuthorityDeliveryDetailReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | RUNTIME_AUTHORITY_DELIVERY_READ; read | `get_runtime_authority_delivery_detail` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3089 | MA; #404 |
| `read.products` (H:495) | `GET /workspaces/{workspace_id}/products`<br>EmptyRequest → RegisteredProductsReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `list_registered_products` **not exposed**; G restricted | O/test_large_read_route_parity.py:313; O/test_read_pages.py:234 | MA; #404 |
| `read.product-detail` (H:496) | `GET /workspaces/{workspace_id}/products/{descriptor_sha256}`<br>EmptyRequest → RegisteredProductDetailReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | INSTANCE_WORKSPACE_READ; read | `get_registered_product` **not exposed**; G restricted | Core HTTP inventory; **test evidence gap** | MA; #404 |
| `read.secret-providers` (H:497) | `GET /workspaces/{workspace_id}/secret-providers`<br>EmptyRequest → SecretProviderCollectionReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | SECRET_PROVIDER_READ; read | `list_secret_providers` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3274; O/test_cpk_server_adapters.py:3288 | MA; #404 |
| `read.secret-provider-detail` (H:502) | `GET /workspaces/{workspace_id}/secret-providers/{provider_id}`<br>EmptyRequest → SecretProviderDetailReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | SECRET_PROVIDER_READ; read | `get_secret_provider_detail` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3306 | MA; #404 |
| `read.secret-references` (H:507) | `GET /workspaces/{workspace_id}/secret-references`<br>EmptyRequest → SecretReferenceCollectionReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | SECRET_PROVIDER_READ; read | `list_secret_references` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3354; O/test_current_metadata_read_pages.py:120 | MA; #407 |
| `read.secret-reference-detail` (H:512) | `GET /workspaces/{workspace_id}/secret-references/{registration_id}`<br>EmptyRequest → SecretReferenceDetailReadResponse | R/_closed_read_arguments + _read_model<br>T.call (route transport) | SECRET_PROVIDER_READ; read | `get_secret_reference_detail` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3370; O/test_cpk_server_adapters.py:3391 | MA; #407 |
| `read.workspace-permissions` (H:528) | `GET /workspaces/{workspace_id}/permissions`<br>WorkspaceAdministrationReadRequest → WorkspacePermissionPage | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; read | `list_workspace_permissions` **not exposed**; G restricted | O/test_postgres_workspace_administration_application.py:107; O/test_postgres_workspace_administration_application.py:163 | MA; #405 |
| `read.workspace-permission` (H:529) | `GET /workspaces/{workspace_id}/permissions/inspect`<br>WorkspaceAdministrationReadRequest → WorkspacePermissionRecord | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; read | `inspect_workspace_permission` std read schema; G restricted | O/test_postgres_workspace_administration_application.py:105 | EX (standard source); #405 |
| `read.workspace-permission-history` (H:530) | `GET /workspaces/{workspace_id}/permissions/history`<br>WorkspaceAdministrationReadRequest → WorkspacePermissionPage | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; read | `list_workspace_permission_history` **not exposed**; G restricted | O/test_postgres_workspace_administration_application.py:198 | MA; #405 |
| `read.managed-runtime-assignments` (H:531) | `GET /workspaces/{workspace_id}/runtime-management`<br>WorkspaceAdministrationReadRequest → ManagedRuntimeAssignmentPage | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; read | `list_managed_runtime_assignments` **not exposed**; G restricted | O/test_postgres_workspace_administration_application.py:132 | MA; #405 |
| `read.managed-runtime-assignment` (H:532) | `GET /workspaces/{workspace_id}/runtime-management/inspect`<br>WorkspaceAdministrationReadRequest → ManagedRuntimeAssignment | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; read | `inspect_managed_runtime_assignment` std read schema; G restricted | O/test_postgres_workspace_administration_application.py:122; O/test_postgres_workspace_administration_application.py:124 | EX (standard source); #405 |
| `read.managed-runtime-assignment-history` (H:533) | `GET /workspaces/{workspace_id}/runtime-management/history`<br>WorkspaceAdministrationReadRequest → ManagedRuntimeAssignmentPage | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; read | `list_managed_runtime_assignment_history` **not exposed**; G restricted | O/test_postgres_workspace_administration_application.py:130 | MA; #405 |
| `read.provider-policy-command` (H:557) | `GET /administration/provider-policies/{logical_provider_id}/commands/{command_id}`<br>ProviderPolicyCommandReadRequest → ProviderPolicyCommandRecordResponse | PP/_decode_provider_policy_request<br>T.call (route transport) | independent ProviderPolicyAdministrationPolicy; read | `get_provider_policy_command` **not exposed**; G restricted | O/test_provider_policy_public_administration.py:211; O/test_provider_policy_public_administration.py:489 | MA; #407 |
| `read.provider-policy-grant` (H:563) | `GET /administration/provider-policies/{logical_provider_id}/grants/{grant_id}`<br>ProviderPolicyGrantReadRequest → ProviderPolicyGrantReadResponse | PP/_decode_provider_policy_request<br>T.call (route transport) | independent ProviderPolicyAdministrationPolicy; read | `get_provider_policy_grant` **not exposed**; G restricted | O/test_provider_policy_public_administration.py:206; O/test_provider_policy_public_administration.py:283 | MA; #407 |
| `read.provider-policy-grants` (H:569) | `GET /administration/provider-policies/{logical_provider_id}/grants`<br>ProviderPolicyGrantListRequest → ProviderPolicyGrantPageResponse | PP/_decode_provider_policy_request<br>T.call (route transport) | independent ProviderPolicyAdministrationPolicy; read | `list_provider_policy_grants` **not exposed**; G restricted | O/test_provider_policy_public_administration.py:373; O/test_provider_policy_public_administration.py:384 | MA; #407 |

## Command operations

All 48 parity commands declare a caller-owned durable idempotency key; the
confidential HTTP-only operation has its own encoded request/receipt owner.
Do not infer atomic external effects or safe retry from a schema or SDK hint.

| Canonical route / H line | HTTP path; request → response | G owner/decoder; HTTP client reference | G authority; effect; Core approval | Standard schema/exposure; G profile | Existing test source reference | Draft disposition / next issue |
| --- | --- | --- | --- | --- | --- | --- |
| `command.workspace-administration.create` (H:601) | `POST /administration/workspaces`<br>CreateWorkspaceAsAdministratorRequest → WorkspaceAdministrationResult | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; command; N | `create_workspace_as_administrator` **not exposed**; G restricted | O/test_postgres_workspace_administration_application.py:55; O/test_postgres_workspace_administration_application.py:83 | MA; #405; G1 |
| `command.workspace-permission.grant` (H:604) | `POST /workspaces/{workspace_id}/permissions/grant`<br>GrantWorkspacePermissionsRequest → WorkspacePermissionResult | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; command; N | `grant_workspace_permissions` **not exposed**; G restricted | O/test_postgres_workspace_administration_application.py:98; O/test_postgres_workspace_administration_application.py:113 | MA; #405; G1 |
| `command.workspace-permission.revoke` (H:607) | `POST /workspaces/{workspace_id}/permissions/revoke`<br>RevokeWorkspacePermissionsRequest → WorkspacePermissionResult | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; command; N | `revoke_workspace_permissions` **not exposed**; G restricted | O/test_postgres_workspace_administration_application.py:101 | MA; #405; G1 |
| `command.managed-runtime-access.grant` (H:610) | `POST /workspaces/{workspace_id}/runtime-management/grant`<br>GrantManagedRuntimeAccessRequest → ManagedRuntimeAssignmentResult | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; command; N | `grant_managed_runtime_access` **not exposed**; G restricted | O/test_postgres_workspace_administration_application.py:123; O/test_postgres_workspace_administration_application.py:126 | MA; #405; G1 |
| `command.managed-runtime-access.revoke` (H:613) | `POST /workspaces/{workspace_id}/runtime-management/revoke`<br>RevokeManagedRuntimeAccessRequest → ManagedRuntimeAssignmentResult | WA/_decode_administration_request<br>T.call (route transport) | independent WorkspaceAdministrationPolicy; command; N | `revoke_managed_runtime_access` **not exposed**; G restricted | O/test_postgres_workspace_administration_application.py:128 | MA; #405; G1 |
| `command.provider-policy.grant` (H:616) | `POST /administration/provider-policies/{logical_provider_id}/grants`<br>GrantProviderPolicyRequest → ProviderPolicyCommandRecordResponse | PP/_decode_provider_policy_request<br>T.call (route transport) | independent ProviderPolicyAdministrationPolicy; external material/policy; N | `grant_provider_policy` **not exposed**; G restricted | O/test_provider_policy_public_administration.py:452; O/test_provider_policy_public_administration.py:565 | MA; #407; G1 |
| `command.provider-policy.revoke` (H:625) | `POST /administration/provider-policies/{logical_provider_id}/grants/{grant_id}/revoke`<br>RevokeProviderPolicyRequest → ProviderPolicyCommandRecordResponse | PP/_decode_provider_policy_request<br>T.call (route transport) | independent ProviderPolicyAdministrationPolicy; external material/policy; N | `revoke_provider_policy` **not exposed**; G restricted | O/test_provider_policy_public_administration.py:207; O/test_provider_policy_public_administration.py:611 | MA; #407; G1 |
| `command.provider-policy.reconcile` (H:634) | `POST /administration/provider-policies/{logical_provider_id}/commands/{command_id}/reconcile`<br>ReconcileProviderPolicyRequest → ProviderPolicyCommandRecordResponse | PP/_decode_provider_policy_request<br>T.call (route transport) | independent ProviderPolicyAdministrationPolicy; external material/policy; N | `reconcile_provider_policy` **not exposed**; G restricted | O/test_provider_policy_public_administration.py:212; O/test_provider_policy_public_administration.py:471 | MA; #407; G1 |
| `command.delegation-key.register` (H:643) | `POST /workspaces/{workspace_id}/delegation-keys`<br>RegisterDelegationSigningKeyRequest → RegisteredDelegationSigningKeyResponse | P/_arguments<br>T.call (route transport) | DELEGATION_KEY_REGISTER; command; N | `register_delegation_key` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3566 | MA; #407; G1 |
| `command.delegation-key.activate` (H:652) | `POST /workspaces/{workspace_id}/delegation-keys/{issuer}/{key_id}/activate`<br>ActivateDelegationSigningKeyRequest → RegisteredDelegationSigningKeyResponse | P/_arguments<br>T.call (route transport) | DELEGATION_KEY_ACTIVATE; command; N | `activate_delegation_key` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3594 | MA; #407; G1 |
| `command.delegation-key.retire` (H:661) | `POST /workspaces/{workspace_id}/delegation-keys/{issuer}/{key_id}/retire`<br>RetireDelegationSigningKeyRequest → RegisteredDelegationSigningKeyResponse | P/_arguments<br>T.call (route transport) | DELEGATION_KEY_RETIRE; command; N | `retire_delegation_key` **not exposed**; G restricted | Core HTTP inventory; **test evidence gap** | MA; #407; G1 |
| `command.delegation-key.revoke` (H:670) | `POST /workspaces/{workspace_id}/delegation-keys/{issuer}/{key_id}/revoke`<br>RevokeDelegationSigningKeyRequest → RegisteredDelegationSigningKeyResponse | P/_arguments<br>T.call (route transport) | DELEGATION_KEY_REVOKE; command; N | `revoke_delegation_key` **not exposed**; G restricted | Core HTTP inventory; **test evidence gap** | MA; #407; G1 |
| `command.gateway-probe.request` (H:679) | `POST /workspaces/{workspace_id}/gateways/{gateway_node_id}/probes`<br>GatewayProbeCommandRequest → GatewayProbeCommandResponse | G/_arguments<br>T.call (route transport) | GATEWAY_PROBE_USE + DELEGATION_KEY_USE + SECRET_PROVIDER_USE; command; N | `request_gateway_probe` **not exposed**; G restricted | O/test_gateway_probes.py:782 | MA; #412 |
| `command.delegation-key.generate` (H:688) | `POST /workspaces/{workspace_id}/delegation-keys/generate`<br>GenerateDelegationKeyRequest → GeneratedDelegationKeyReceipt | E/_arguments<br>T.call (route transport) | DELEGATION_KEY_GENERATE + DELEGATION_KEY_REGISTER; external material/policy; N | `generate_delegation_key` **not exposed**; G restricted | O/test_delegation_key_generation_commands.py:437; O/test_delegation_key_generation_commands.py:459 | MA; #407; G1 |
| `command.secret-material.provision` (H:695) | `POST /workspaces/{workspace_id}/secret-material/provision`<br>ProvisionSecretMaterialRequest → ProvisionedSecretMaterialReceipt | E/_arguments<br>no model-facing private intake | SECRET_MATERIAL_PROVISION + SECRET_PROVIDER_REGISTER; external material/policy; HTTP-only owner | no parity binding; G restricted | O/test_postgres_application_initial_context.py:187; O/test_secret_material_provision_commands.py:101 | DR: confidential HTTP-only; G2; #407 |
| `command.delegation-key-generation.reconcile` (H:702) | `POST /workspaces/{workspace_id}/delegation-key-generations/{request_id}/reconcile`<br>ReconcileDelegationKeyGenerationRequest → GeneratedDelegationKeyReceipt | E/_arguments<br>T.call (route transport) | DELEGATION_KEY_GENERATE + DELEGATION_KEY_REGISTER; command; N | `reconcile_delegation_key_generation` **not exposed**; G restricted | O/test_delegation_key_generation_commands.py:470 | MA; #407; G1 |
| `command.workspace.create` (H:709) | `POST /workspaces`<br>CreateWorkspaceRequest → WorkspaceReadResponse | P/_arguments<br>T.call (route transport) | HUB_INSTANCE_CREATE; command; N | `create_workspace` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1617; O/test_cpk_server_adapters.py:2465 | DR: static-only legacy create; #405 |
| `command.product.import` (H:718) | `POST /workspaces/{workspace_id}/products/import`<br>ImportProductDescriptorRequest → RegisteredProductResponse | P/_arguments<br>T.call (route transport) | INSTANCE_WORKSPACE_EDIT; command; N | `import_product_descriptor` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1657; O/test_cpk_server_adapters.py:2481 | MA; #406; G1 |
| `command.image-pull-authority.register` (H:727) | `POST /workspaces/{workspace_id}/image-pull-authorities`<br>RegisterImagePullAuthorityRequest → RegisteredImagePullAuthorityResponse | P/_arguments<br>T.call (route transport) | INSTANCE_WORKSPACE_EDIT; command; N | `register_image_pull_authority` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1633; O/test_cpk_server_adapters.py:2850 | MA; #406; G1 |
| `command.runtime-authority.register` (H:736) | `POST /workspaces/{workspace_id}/runtime-authorities`<br>RegisterRuntimeAuthorityRequest → RegisteredRuntimeAuthorityResponse | P/_arguments<br>T.call (route transport) | RUNTIME_AUTHORITY_REGISTER; command; N | `register_runtime_authority` **not exposed**; G restricted | O/test_cpk_server_adapters.py:2900; O/test_cpk_server_adapters.py:2929 | MA; #406; G1 |
| `command.runtime-authority.revoke` (H:745) | `POST /workspaces/{workspace_id}/runtime-authorities/{authority_ref}/revoke`<br>RevokeRuntimeAuthorityRequest → RegisteredRuntimeAuthorityResponse | P/_arguments<br>T.call (route transport) | RUNTIME_AUTHORITY_REVOKE; command; N | `revoke_runtime_authority` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3156; O/test_cpk_server_adapters.py:3177 | MA; #406; G1 |
| `command.runtime-authority-delivery.register` (H:754) | `POST /workspaces/{workspace_id}/runtime-authority-deliveries`<br>RegisterRuntimeAuthorityDeliveryRequest → RegisteredRuntimeAuthorityDeliveryResponse | P/_arguments<br>T.call (route transport) | RUNTIME_AUTHORITY_DELIVERY_REGISTER; command; N | `register_runtime_authority_delivery` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3026; O/test_cpk_server_adapters.py:3050 | MA; #406; G1 |
| `command.runtime-authority-delivery.revoke` (H:763) | `POST /workspaces/{workspace_id}/runtime-authority-deliveries/{authority_ref}/revoke`<br>RevokeRuntimeAuthorityDeliveryRequest → RegisteredRuntimeAuthorityDeliveryResponse | P/_arguments<br>T.call (route transport) | RUNTIME_AUTHORITY_DELIVERY_REVOKE; command; N | `revoke_runtime_authority_delivery` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3110; O/test_cpk_server_adapters.py:3136 | MA; #406; G1 |
| `command.ingress-authority.register` (H:772) | `POST /workspaces/{workspace_id}/ingress-authorities`<br>RegisterIngressAuthorityRequest → RegisteredIngressAuthorityResponse | P/_arguments<br>T.call (route transport) | INGRESS_AUTHORITY_REGISTER; command; N | `register_ingress_authority` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1750; O/test_cpk_server_adapters.py:1764 | MA; #406; G1 |
| `command.ingress-authority.revoke` (H:781) | `POST /workspaces/{workspace_id}/ingress-authorities/{authority_ref}/revoke`<br>RevokeIngressAuthorityRequest → RegisteredIngressAuthorityResponse | P/_arguments<br>T.call (route transport) | INGRESS_AUTHORITY_REVOKE; command; N | `revoke_ingress_authority` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1834; O/test_cpk_server_adapters.py:1854 | MA; #406; G1 |
| `command.secret-provider.register` (H:790) | `POST /workspaces/{workspace_id}/secret-providers`<br>RegisterSecretProviderRequest → RegisteredSecretProviderResponse | P/_arguments<br>T.call (route transport) | SECRET_PROVIDER_REGISTER; command; N | `register_secret_provider` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3240; O/test_cpk_server_adapters.py:3252 | MA; #406; G1 |
| `command.secret-provider.revoke` (H:799) | `POST /workspaces/{workspace_id}/secret-providers/{provider_id}/revoke`<br>RevokeSecretProviderRequest → RegisteredSecretProviderResponse | P/_arguments<br>T.call (route transport) | SECRET_PROVIDER_REVOKE; command; N | `revoke_secret_provider` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3452 | MA; #406; G1 |
| `command.secret-reference.register` (H:808) | `POST /workspaces/{workspace_id}/secret-references`<br>RegisterSecretReferenceRequest → RegisteredSecretReferenceResponse | P/_arguments<br>T.call (route transport) | SECRET_PROVIDER_REGISTER; command; N | `register_secret_reference` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3326; O/test_cpk_server_adapters.py:3535 | MA; #407; G1 |
| `command.secret-reference.revoke` (H:817) | `POST /workspaces/{workspace_id}/secret-references/{registration_id}/revoke`<br>RevokeSecretReferenceRequest → RegisteredSecretReferenceResponse | P/_arguments<br>T.call (route transport) | SECRET_PROVIDER_REVOKE; command; N | `revoke_secret_reference` **not exposed**; G restricted | O/test_cpk_server_adapters.py:3411; O/test_cpk_server_adapters.py:3431 | MA; #407; G1 |
| `command.operation-session.start` (H:826) | `POST /workspaces/{workspace_id}/sessions`<br>StartOperationSessionRequest → OperationCommandResult | L/_arguments<br>T.call (route transport) | INSTANCE_WORKSPACE_EDIT; command; N | `start_operation_session` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1679; O/test_managed_selected_update_execution.py:109 | MA; #411 |
| `command.operation-session.close` (H:835) | `POST /workspaces/{workspace_id}/sessions/{session_id}/close`<br>CloseOperationSessionRequest → OperationCommandResult | L/_arguments<br>T.call (route transport) | INSTANCE_WORKSPACE_EDIT; command; N | `close_operation_session` **not exposed**; G restricted | Core HTTP inventory; **test evidence gap** | MA; #411 |
| `command.operation-session.cancel` (H:844) | `POST /workspaces/{workspace_id}/sessions/{session_id}/cancel`<br>CancelOperationSessionRequest → OperationCommandResult | L/_arguments<br>T.call (route transport) | INSTANCE_WORKSPACE_EDIT; command; N | `cancel_operation_session` **not exposed**; G restricted | Core HTTP inventory; **test evidence gap** | MA; #411 |
| `command.operation-session.record-action` (H:853) | `POST /workspaces/{workspace_id}/sessions/{session_id}/actions`<br>RecordOperationActionRequest → OperationCommandResult | L/_arguments<br>T.call (route transport) | INSTANCE_WORKSPACE_EDIT; command; N | `record_operation_action` **not exposed**; G restricted | Core HTTP inventory; **test evidence gap** | MA; #411 |
| `command.desired-topology-draft.create` (H:862) | `POST /workspaces/{workspace_id}/desired-topology-drafts`<br>CreateDesiredTopologyDraftRequest → DesiredTopologyDraftResult | P/_arguments<br>TopologyClient.draft_save | INSTANCE_WORKSPACE_EDIT; command; N | `create_desired_topology_draft` **not exposed**; G restricted | O/test_draft_catalogue_adapters.py:36; O/test_draft_catalogue_adapters.py:73 | MA; #408 |
| `command.desired-topology-draft.revise` (H:871) | `POST /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/revisions`<br>ReviseDesiredTopologyDraftRequest → DesiredTopologyDraftResult | P/_arguments<br>TopologyClient.draft_revise | INSTANCE_WORKSPACE_EDIT; command; N | `revise_desired_topology_draft` **not exposed**; G restricted | O/test_draft_catalogue_adapters.py:42; O/test_draft_catalogue_adapters.py:74 | MA; #408 |
| `command.desired-topology-draft.select` (H:880) | `POST /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/select`<br>SelectDesiredTopologyDraftRequest → DesiredTopologyDraftSelectionResult | P/_arguments<br>TopologyClient.draft_select | INSTANCE_WORKSPACE_EDIT; command; N | `select_desired_topology_draft` **not exposed**; G restricted | O/test_draft_selection_adapters.py:70; O/test_receiver_admission_formats.py:100 | MA; #408 |
| `command.desired-topology-draft.delete` (H:889) | `POST /workspaces/{workspace_id}/desired-topology-drafts/{draft_id}/delete`<br>DeleteDesiredTopologyDraftRequest → DesiredTopologyDraftDeletionResult | P/_arguments<br>T.call (route transport) | INSTANCE_WORKSPACE_EDIT; command; N | `delete_desired_topology_draft` **not exposed**; G restricted | O/test_draft_selection_adapters.py:70 | MA; #408 |
| `command.desired-graph.set` (H:898) | `POST /workspaces/{workspace_id}/graphs/desired`<br>SetDesiredGraphRequest → DesiredGraphEditResult | P/_arguments<br>T.call (route transport) | INSTANCE_WORKSPACE_EDIT; command; S | `set_desired_graph` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1141; O/test_cpk_server_adapters.py:1694 | MA; #408 |
| `command.deployment.plan` (H:907) | `POST /workspaces/{workspace_id}/plans`<br>PlanDeploymentRequest → PlanDeploymentResponse | P/_arguments<br>T.call (route transport) | PLAN_REQUEST; command; S | `plan_deployment` **not exposed**; G restricted | O/test_cpk_server_adapters.py:660; O/test_cpk_server_adapters.py:2181 | MA; #409 |
| `command.deployment.prepare` (H:916) | `POST /workspaces/{workspace_id}/deployments/prepare`<br>PrepareDeploymentProgramRequest → DeploymentPreparationResponse | P/_arguments<br>TopologyClient.plan | INSTANCE_WORKSPACE_EDIT + PLAN_REQUEST; command; S | `prepare_deployment` std prepare schema; G restricted | O/test_cpk_server_adapters.py:660; O/test_cpk_server_adapters.py:1923 | EX (standard source); #409 |
| `command.approval.request` (H:925) | `POST /workspaces/{workspace_id}/plans/{plan_id}/approval`<br>ApprovalRequestRequest → ApprovalRequestResponse | A/_arguments<br>T.call (route transport) | PLAN_REQUEST; command; S | `request_approval` **not exposed**; G restricted | O/test_cpk_server_adapters.py:942; O/test_cpk_server_adapters.py:1050 | MA; #410 |
| `command.approval.decide` (H:934) | `POST /workspaces/{workspace_id}/approvals/{approval_id}/decision`<br>ApprovalDecisionRequest → ApprovalDecisionResponse | A/_arguments<br>TopologyClient.apply (reference only; G1) | PLAN_APPROVE OR PLAN_APPROVE_DESTRUCTIVE; command; D | `decide_approval` **not exposed**; G restricted | O/test_cpk_server_adapters.py:2305; O/test_cpk_server_adapters.py:2587 | MA; #410 |
| `command.deployment.admit` (H:943) | `POST /workspaces/{workspace_id}/plans/{plan_id}/admission`<br>AdmitDeploymentRequest → AdmittedRunResponse | D/_arguments<br>TopologyClient.apply | PLAN_EXECUTE; command; C | `admit_deployment` **not exposed**; G restricted | O/test_cpk_server_adapters.py:1110; O/test_cpk_server_adapters.py:2619 | MA; #411 |
| `command.run.claim` (H:952) | `POST /workspaces/{workspace_id}/runs/{run_id}/claim`<br>ClaimRunRequest → ClaimRunResponse | L/_arguments<br>TopologyClient.apply | WORKER/SERVICE: EXECUTION_OPERATE; command; C | `claim_run` **not exposed**; G restricted | O/test_cpk_server_adapters.py:590; O/test_cpk_server_adapters.py:620 | MA; #411 |
| `command.run.start` (H:961) | `POST /workspaces/{workspace_id}/runs/{run_id}/start`<br>StartRunRequest → ActivityRunTransitionResult | E/_arguments<br>TopologyClient.apply | WORKER/SERVICE: EXECUTION_OPERATE; command; C | `start_run` **not exposed**; G restricted | O/test_cpk_server_adapters.py:319; O/test_cpk_server_adapters.py:359 | MA; #411 |
| `command.deployment.execute` (H:970) | `POST /workspaces/{workspace_id}/runs/{run_id}/execute`<br>ExecuteDeploymentRequest → ExecutionRunResponse | E/_arguments<br>TopologyClient.apply | WORKER/SERVICE: EXECUTION_OPERATE; external/destructive; C | `execute_deployment` **not exposed**; G restricted | O/test_cpk_server_adapters.py:324; O/test_cpk_server_adapters.py:364 | MA; #411 |
| `command.deployment.reobserve-connector` (H:979) | `POST /workspaces/{workspace_id}/runs/{run_id}/reobserve-connector`<br>ReobserveConnectorConnectionRequest → ExecutionRunResponse | E/_arguments<br>T.call (route transport) | WORKER/SERVICE: EXECUTION_OPERATE; command; C | `reobserve_connector_connection` **not exposed**; G restricted | O/test_managed_application_chain.py:746; O/test_managed_application_chain.py:828 | MA; #412 |
| `command.graph.advance-current` (H:988) | `POST /workspaces/{workspace_id}/runs/{run_id}/advance-current-graph`<br>AdvanceCurrentGraphRequest → CurrentGraphAdvancementResult | L/_arguments<br>TopologyClient.apply | WORKER/SERVICE: EXECUTION_OPERATE; command; C | `advance_current_graph` **not exposed**; G restricted | O/test_cpk_server_adapters.py:288; O/test_cpk_server_adapters.py:369 | MA; #411 |
| `command.recovery.decide` (H:997) | `POST /workspaces/{workspace_id}/runs/{run_id}/recovery`<br>RecoveryDecisionRequest → RecoveryDecisionResponse | U (no recovery handler)<br>T.call (route transport) | WORKER/SERVICE: EXECUTION_OPERATE; command; C | `decide_recovery` **not exposed**; G restricted | O/test_cpk_server_adapters.py:642; O/test_cpk_server_adapters.py:2832 | MO: G3; #412 |

## Pinned test reference index

Links below resolve the short row references. A line number is recorded in the
row; these are source references, not claims that every referenced fixture is a
complete success/negative-case proof. All future laws must be checked at the
selected execution cohort, rather than importing a newer owner by accident.

- [O/test_cpk_server_adapters.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_cpk_server_adapters.py)
- [O/test_current_metadata_read_pages.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_current_metadata_read_pages.py)
- [O/test_delegation_key_generation_commands.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_delegation_key_generation_commands.py)
- [O/test_desired_topology_drafts.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_desired_topology_drafts.py)
- [O/test_draft_catalogue_adapters.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_draft_catalogue_adapters.py)
- [O/test_draft_selection_adapters.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_draft_selection_adapters.py)
- [O/test_gateway_probe_read_pages.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_gateway_probe_read_pages.py)
- [O/test_gateway_probes.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_gateway_probes.py)
- [O/test_large_read_route_parity.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_large_read_route_parity.py)
- [O/test_managed_application_chain.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_managed_application_chain.py)
- [O/test_managed_selected_update_execution.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_managed_selected_update_execution.py)
- [O/test_postgres_application_initial_context.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_postgres_application_initial_context.py)
- [O/test_postgres_workspace_administration_application.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_postgres_workspace_administration_application.py)
- [O/test_postgres_workspace_inventory.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_postgres_workspace_inventory.py)
- [O/test_provider_policy_public_administration.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_provider_policy_public_administration.py)
- [O/test_read_pages.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_read_pages.py)
- [O/test_receiver_admission_formats.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_receiver_admission_formats.py)
- [O/test_receiver_authoring_context.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_receiver_authoring_context.py)
- [O/test_secret_material_provision_commands.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_secret_material_provision_commands.py)
- [O/test_workload_verifier_configuration.py](https://github.com/OpenJ92/control-plane-kit/blob/70154b6698e101159326b08646f2dba90dda87cd/control-plane-kit-operations/tests/test_workload_verifier_configuration.py)
- [S/docker_image_update_selection.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/docker_image_update_selection.py)
- [S/dynamic_setup_fixtures.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/dynamic_setup_fixtures.py)
- [S/live_docker_image_update.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/live_docker_image_update.py)
- [S/live_unlisted_receiver.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/live_unlisted_receiver.py)
- [S/managed_provider_selection_acceptance.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/managed_provider_selection_acceptance.py)
- [S/protected_input_preparation.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/protected_input_preparation.py)
- [S/receiver_acceptance_operations.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/receiver_acceptance_operations.py)
- [S/test_client_read_queries.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/test_client_read_queries.py)
- [S/test_confidential_transport.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/test_confidential_transport.py)
- [S/test_http_mcp_boundaries.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/test_http_mcp_boundaries.py)
- [S/test_image_bootstrap.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/test_image_bootstrap.py)
- [S/test_provider_policy_composition.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/test_provider_policy_composition.py)
- [S/test_root_complete_setup.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/test_root_complete_setup.py)
- [S/test_topology_client_catalogue.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/test_topology_client_catalogue.py)
- [S/test_topology_client_report.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/test_topology_client_report.py)
- [S/test_topology_client.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/test_topology_client.py)
- [S/workspace_setup_acceptance.py](https://github.com/OpenJ92/control-plane-kit-servers/blob/0610e9454dd9a75a6e6bf5e89fe281c8631cccaa/products/cpk_server/tests/workspace_setup_acceptance.py)

Additional governing transport/cohort proofs (S):
[test_standard_mcp.py](../products/cpk_server/tests/test_standard_mcp.py),
[test_standard_mcp_planning.py](../products/cpk_server/tests/test_standard_mcp_planning.py),
[test_grandparent_mcp.py](../products/cpk_server/tests/test_grandparent_mcp.py),
[test_http_mcp_boundaries.py](../products/cpk_server/tests/test_http_mcp_boundaries.py),
[test_revision_history_composition.py](../products/cpk_server/tests/test_revision_history_composition.py),
[test_confidential_transport.py](../products/cpk_server/tests/test_confidential_transport.py),
[test_provider_policy_composition.py](../products/cpk_server/tests/test_provider_policy_composition.py),
[test_protected_input_composition.py](../products/cpk_server/tests/test_protected_input_composition.py),
[test_operations_application_factory.py](../products/cpk_server/tests/test_operations_application_factory.py).
Core's [test_http_api_contract.py](https://github.com/OpenJ92/control-plane-kit/blob/f56bb5c4cfde76764d39c5377d4270c5b23c3ba1/control-plane-kit-core/tests/test_http_api_contract.py)
and adapter/command parity contract tests own canonical inventory, not the
Servers adapter. Reuse those owners; this draft creates no duplicate registry.

## Preserved laws and MCP differences

This issue is **non-executable-scaffold**: exhaustive source/link reconciliation,
not an artificial failing test for prose. The following are compact law cards
for downstream dry runs, with their existing source context:

| Law / classification for the implementation | Existing reference | Observable result and negative cases to preserve |
| --- | --- | --- |
| Auth before sensitive decode; isomorphic | HTTP/MCP boundary authentication tests; confidential transport tests | Wrong/missing bearer denies before owner dispatch; changed bearer is checked on each call; duplicate/nonfinite/oversized/deep input gets bounded refusal. Raw collection may precede auth under its explicit byte cap; do not claim no body bytes were read. |
| Current owner authorization; isomorphic | O RouteAuthorizationPolicy, workspace/provider administration and current effect policies; S provider-policy/protected-input tests | Resolve current principal/workspace and independent administration policy before effects. CPK denial proves no provider acquisition; a separately tested Secrets policy denial may occur after provider contact. Denied diagnostics never imply absent state. |
| Read framing and redaction; isomorphic with explicit schema adaptation | S test_http_mcp_boundaries (paged reads, authoring context, closed grammar); standard/grandparent SDK parity tests | Preserve exact workspace/revision/cursor scope, limits and safe owner fields. HTTP query strings decode to typed owner values; MCP object fields do not need byte-identical transport representation. Graph projections are redacted observations, not executable source exports. |
| Saved intent and correlation; isomorphic | S StandardMcpPlanningTests and G O _prepare_deployment:1185; O deployment-program/preparation tests | Pass exact saved revision, current/Desired authored+projection fences, Desired generation and durable idempotency key. Preserve no-changes/review-blocked/approval-required and plan/approval/session identities. Reconnect reads are observations; a lost response does not prove rollback. Do not choose a newest record or blindly replay. |
| Managed intent; new MCP schema, preserved HTTP law | G O _managed_verification_planning_intent:1245; S managed startup/native-composition tests | G HTTP accepts its exact managed-verification intent; standard SDK prepare rejects any extra input and has no such field. #409 must explicitly adapt the selected owner contract, not silently use D885 or open arbitrary payload forwarding. |
| Human decision and execution fence; isomorphic plus #396 product restriction | O Approval/Admission/Lifecycle/Execution services and parity C policies; client workflow reference | Agent may request/read approval. Human website identity decides the exact durable plan. Admission/execution rechecks current approval, principal kind, worker authority and lease fence. No agent self-grant, human impersonation or transplant of TopologyClient.apply's optional self-decision path. |
| Bounds and safe uncertain outcome; isomorphic/strengthened where justified | S standard MCP budget/error/cancellation and awaited execution tests | Input route budget, output route budget and bounded error budget all apply; SDK envelopes/lifecycle are protocol-specific new mechanics. A 503/failed send/cancel can follow a committed owner action. Preserve committed/failed/unknown distinctions and durable references; no retry/journal in adapter. |
| Exposure policy; new SDK surface over existing owners | S GrandparentMcpTests (four reads and direct-command refusal); Core HTTP_ONLY restriction | Hidden tool cannot be reached by direct call, even without client allowlist. Confidential provision remains absent before argument access. Discovery/schema expansion requires reviewed #403 disposition and milestone gates, not just adding every Core parity name. |

### Concrete trace for #163 managed preparation

At S server.py:603 create_app installs canonical HTTP routes and constructs
StandardMcpAdapter over the same application. In G, boundary._decode_http_payload
produces typed argument data; CpkServerOperationsApplication._prepare resolves
current workspace authority; CpkServerPlanningService dispatches
command.deployment.prepare to O _prepare_deployment. That helper constructs
PrepareDeploymentProgram with exact desired identity/fences/key and
managed_verification (or the separately admitted HTTP sample intent). Operations
DeploymentProgram/Interpreter owns session/plan/approval truth; the shared
factory supplies the existing native registrations, secret metadata and effect
owners. None of this can be replaced by an MCP-only planner.

For standard MCP the current closed prepare schema requires workspace_id,
draft_id, revision >=1, expected_current/expected_desired each with
authored_graph_id and realized_projection_id, expected_desired_graph_revision
>=1, title and idempotency_key; additionalProperties is false. It accepts no
inline graph, session override, managed intent or derivation override. G's
initial profile rejects prepare before dispatch. Thus the last established
boundary is HTTP managed-owner composition plus isolated/source MCP reads;
the smallest missing connection for #163 planning is a reviewed #409 schema and
cohort-preserving dispatch after #399/#403/#408. It is not new planning semantics.

An additional schema/cohort distinction needs #409 review: G701's HTTP owner
accepts a nonnegative Desired generation and optional expected_desired, while
the current standard MCP schema requires a positive generation and a complete
expected_desired object. G also has inline input support; restricting the future
tool to saved input can be deliberate, but narrowing initial/empty Desired
fences must not happen accidentally. Preserve the owner laws or record the
reviewed restriction and negative cases before exposing a new schema.

## Owner gaps and deliberate non-goals

These are named prerequisite proposals, **not new interfaces already accepted**.
North must link the concrete owning-repository issue or accept a deliberate
unsupported disposition before the dependent implementation claims completeness.

| Gap | Existing source truth | Owner prerequisite / downstream disposition |
| --- | --- | --- |
| **G1 — consequential administration approval** | Core declares N for registration, permission, provider-policy and material commands. O WA/PP and planning/material owners enforce their present policies; they do not turn a website plan approval into generic approval of those earlier actions. | Before #405/#406/#407 give an agent consequential powers, Operations must specify which non-plan actions require human consent, how the exact request/decision binds to current actor/target/version and execution, and what existing website surface consumes it. Link a concrete Operations prerequisite for any missing contract; do not implement it in MCP, grant the agent its own approver scope, or treat an app tool prompt as CPK approval. No new issue has been filed by this draft. |
| **G2 — private provisioning ingress** | command.secret-material.provision is the sole HTTP_ONLY route, with no parity binding; O execution refuses non-HTTP before private payload access. Encoded private intake, independent provider authority and safe receipt/readback are existing owners. | #407 must use a supported operator-private handoff or request an owning contract for opaque private delivery. Literal secrets remain outside model-visible tools, errors, hashes and transcripts. Reference/version receipt reads are separate safe projections. Do not remove HTTP_ONLY, return a secret value, or assume the G server's absent Secrets distribution proves provider availability. |
| **G3 — generic recovery command unavailable** | O cpk_server_services wires RECOVERY to CpkServerUnsupportedService (501 after authority checks). A Core route/parity binding is not a concrete recovery implementation. Existing bounded reobserve-connector is a different explicit owner action. | #412/#411 require an Operations-owned public recovery contract or reviewed unsupported disposition. Inspect/reuse existing recovery/lease owners; do not invent retry, rollback, compensation or repair in adapter. #412 is the tracking child; a distinct owner prerequisite must be linked before implementing generic recovery. |
| **G4 — ambiguous lost preparation response** | There is no public lookup by preparation idempotency key. Exact revision preparations and session plans can reveal known durable associations; multiple matching preparations can remain ambiguous. | #409/#413 must preserve unknown association and use existing authoritative references. If a stronger lookup is required, specify it with the Operations preparation/read owner first. A local journal or newest-record heuristic cannot fill this gap. |
| **G5 — fresh general health/recovery observation** | Stored observed-state/probe timeline reads are not fresh checks. gateway-probe.request and reobserve-connector have their own scoped effects and fences; managed plan observations have separate owners. | #412 must name the exact existing fresh-observation owner per target family. A generic fresh-health command with no suitable route requires an owning Operations contract, not a GET that silently probes or source/private provider access. Existing #412 tracks this refinement. |
| **G6 — cohort difference in workspace inventory** | G H has read.workspaces and O WorkspaceInventoryReadService/current dynamic inventory policy. Selected D Core has no read.workspaces route. | #404/#405 must explicitly select/adopt an owner/cohort before advertising discovery. This is not proof that the Core owner is universally missing, nor permission to change selected dependency pins opportunistically. |

### Supported workflows not represented by a new route

| Canonical owner operation / workflow | Existing equivalent and disposition | Tests/evidence still required |
| --- | --- | --- |
| Initial CPK/Secrets/DB process and credential bootstrap | **EB**: existing bootstrap/commissioning boundaries precede public routes. They do not become model shell tools. | Existing bootstrap owner receipts and separately authorized installation/client configuration; no new private access here. |
| Pure graph validation and receiver authoring | Existing Core graph codecs/validators plus client.prepare_receiver_configuration and HTTP receiver-authoring-context; validation is also enforced by create/revise/select owners. No standalone validate HTTP route is declared. #408 must choose composition or an owner prerequisite explicitly. | Existing graph-authoring/receiver tests; missing dedicated standard MCP schema and installed validation witness. Do not treat redacted read graphs as original source. |
| Exact material version selection | References/version selections are part of admitted authored topology and owner material receipts, not a new generic resolve-secret MCP tool. #407 + #408 own the safe sequence. | Provider metadata policy, exact returned version identity, no secret value in readback; selected provider capabilities remain unverified by this offline matrix. |
| Teardown/removal | Desired topology change → plan → exact human approval → approved execution; no generic Docker prune/delete endpoint. #411 preserves supported destruction/retention/ownership laws. | Coherent owner teardown/partial-failure and installed approved-loop evidence; no automatic cleanup or compensation. |
| Component capabilities / graph prerequisites / guidance | Existing products/control-surface/receiver-context and owner admission facts feed #404/#413. No arbitrary endpoint/method forwarding or model-text execution. A new component-catalogue route is not assumed. | Missing standard adapters and prerequisite-source mapping; guidance must distinguish forbidden/unavailable/unsupported/missing, and treat graph prose as untrusted data. |
| Lease recovery and interrupted external work | Current-state/plan/run/events plus named Operations recovery owners, with G3 limitation at the public generic command. | Approved exact supported recovery action and durable committed/failed/unknown result; never redispatch on uncertain result. |

## #163 path and operator-private boundaries

The path is a sequence through the matrix, not permission to resume paused #163:

1. Complete #399's real installed four reads. Inspect workspace, Desired and the
   exact saved revision/attempts; no fixture substitutes for existing state.
2. #404/#405 expose authorized discovery, receiver context, product catalogue,
   runtime/provider/ingress metadata and current permissions. A denied read is
   not a missing resource. Any permission/management changes wait for G1.
3. #406 admits exact runtime delivery, product/ingress/provider registrations
   with the existing owners; registration is not provisioning a new runtime.
4. #407 resolves approved material/reference/version setup using the selected
   provider's supported intents. Operator-private values and private custody
   stay outside MCP; retain only safe exact receipt/reference/version evidence.
5. #408 validates and saves/revises the authored topology, then explicitly
   selects the intended revision with its current Desired fences. A historical
   revision becomes a new desired intent only through those existing owners.
6. #409 prepares that saved revision with the G managed SQL/HTTP readiness
   intent, exact current/Desired lineage/generation and durable correlation key.
7. #410 presents the exact plan/approval request and observes Jacob's website
   decision; it never uses the ordinary agent as the human approver.
8. #411 admits/claims/executes the exact currently approved plan using the
   existing worker authority and lease fence. Query runs/events/outcomes and
   advance Current only through the existing fenced owner.
9. #412/#413 inspect fresh supported health, stopped/partial/unknown outcomes
   and owner-derived next steps. A new request or retry needs its own current
   authority and approval; no automatic recovery.
10. #414 proves the complete installed workflow. #163 capstone acceptance,
    private credential delivery, publication and real provider/deployment effects
    remain their own explicit releases. Helper retirement stays #340/PR #353
    and #342, not a parallel removal project.

## Review, validation and handoff

- Coverage audit: 102 distinct G rows =53 reads+49 commands; P=53+48, excluded
  exactly confidential provision. D=101, missing exactly read.workspaces.
  These are source-text inventory comparisons, not runtime discovery results.
- This draft used existing tests and inventories without executing application
  code, importing owner packages, contacting the installation or running Docker.
  Documentation validation is git diff --check plus pinned source/link checks.
  No artificial red test or implementation acceptance is claimed.
- Remaining review: every row's proposed disposition and downstream owner issue;
  resolve G1/G2/G3/G5 contract prerequisites before corresponding implementations;
  map the eight explicitly noted route-test references before claiming their
  behavioral proof; review D/G-specific schemas and selected optional-port
  support in each implementation handoff.
- Security/history: no new route, authority, durable state, provider capability
  or network exposure. Future commands retain existing sessions/actions,
  plans/approvals/runs/events, bounds/redaction and transactional/effect owners.
  A missing/unavailable response does not erase a possible durable action.
- Mandatory gates are proposed in [the roadmap learning record](learning/1813/run-0001.md#mcp-396403-proposed-milestone-review-gates).
  #399, matrix acceptance, human approval/administration contracts and expanded
  effects must remain ordered. This parallel prose work accepts no milestone.

Decision log: chose the existing canonical HTTP/parity inventory plus actual
SDK exposure and G701 owner mappings. Rejected equating parity declarations,
legacy dispatch or permission denial with installed capability; rejected a new
adapter-owned command vocabulary, policy/planner, journal or general HTTP proxy.
Next reviewer is Meridian via North. North owns issue/PR disposition into
roadmap/1813-runtime-control; this branch changes documentation only.
