# Temporary operational framework retirement

Status: **Draft inventory; source retirement and acceptance pending.**
Owner: [Servers #340](https://github.com/OpenJ92/control-plane-kit-servers/issues/340).
Final acceptance depends on [G/#342](https://github.com/OpenJ92/control-plane-kit-servers/issues/342).
North released inventory and independent preparation in parallel with Operations
CI; the existing G-before-H merge boundary remains.

This inventory describes Servers base `ce3192ee91ccd5a3b21a1904f85de35cb9370479`.
Its manifest selects Core/Operations `fec0816281aeb83ede98616adcc4f96dfe5777a8`,
Interpreters `27457ca5eab6ae96d78146e7ea0c998b986feab3`, SDK
`cd4722fbfb942e7c2467a39b3cd0e32ded4a90ac`, and Secrets
`46e0718664c425d002f2420a6ad1f996be62b2c5`.
The replacement contract map below uses accepted upstream Core/Operations
`7afef43f3d3b981094e37dcb3062b6e3a4f3d674` and G's recorded trace. Adoption in
Servers is separate [#351/#352](https://github.com/OpenJ92/control-plane-kit-servers/pull/352)
work. No dependency, installed service or deployed image is changed here.

## What changes at this checkpoint

The old #221 diagnostic invocation recipe moves to an explicitly historical
learning record. Its former operator-guide location explains the pending public
replacement and no longer presents direct Operations execution as a routine
operator procedure. Historical text, source, tests and evidence remain intact.
No executable path is deleted or redirected at this checkpoint: the required
replacement proof is not yet complete. This is a documentation removal diff,
not a claim that H's source-removal requirement has passed.

## Inventory and removal accounting

Paths in the table are repository-relative. Function names identify the affected
behavior, not a new interface. “Replace” and “delete” are the proposed final
source dispositions after the named proof; **pending** means the current code
remains available and receives no G acceptance credit for its bypass behavior.

| Artifact / entrypoint | Active callers or consumers at this base | Final disposition and required replacement |
| --- | --- | --- |
| `scripts/cpk_server_hosted_activity.py::HostedWorkflow`, `_bootstrap_workspace`, `create_workspace` | `cpk_server_hosted_activity_smoke.sh`; recursive, recursive-TLS, remote-TLS and secret-provider Python controllers; `tests/test_hosted_activity_readiness.py`; product bootstrap/delegation/rotation tests | **Replace, pending G.** Keep only bounded public command submission/polling/assertions. Existing create calls legacy `POST /workspaces`; dynamic enrollment uses administrator create and distinct ordinary/management grants below. Do not copy planning, receipt or claim state machines into a new client. |
| Hosted `_execute_to_completion`, `_sync_runtime_networks`, `_disconnect_runtime_networks`; direct sync calls in gateway scenarios | `HostedWorkflow.execute_to_completion`, gateway toggle/private scenarios; secret-provider `_execute_until_terminal` and Cloudflare custody; recursive controllers have separate sync helpers | **Delete repair from maintained acceptance, pending declared-connectivity proof in G.** Execute through CPK with already admitted topology/runtime connectivity. G must explicitly pass `sync_runtime_networks=False` when reusing the existing helper. No replacement Docker-connect command or harness retry. |
| Hosted `_direct_gateway_grant`, `_signed_gateway_capability`, `_direct_gateway_probe` and secret-provider `_direct_gateway_capability` / denial probes | Hosted private/public gateway scenarios; `_assert_live_gateway_denial_matrix`; gateway denial/access-path tests | **Replace routine operator probing with public observation; retain only separately justified product-boundary negative tests.** `request_gateway_probe` and its reads cover the existing gateway-probe contract, not automatically the distinct signed self-health readiness diagnostic. G binds the actual required health contract. |
| `scripts/cpk_server_secret_provider_source_live.py::_owned_cloudflare_epoch_evidence`, `_load_exact_owned_ingress_resources`, `_load_all_exact_owned_ingress_resources`, `_load_connector_run_rows`, `_assert_owned_cloudflare_resources_removed`, `_assert_cloudflare_provider_correlation`, `_operations_correlations` | Cloudflare custody/epoch assertions, abort cleanup, connector reconstruction and provider/run correlation assertions in this controller; abort/lifecycle tests | **Replace private Operations SQL with public evidence, pending G's existing projection coverage check.** Run events/current graph already have public reads; exact ingress epoch/status/IDs and acknowledged partial-allocation evidence must be verified field by field. Registration metadata alone is insufficient. Do not manufacture ownership from graph state or current policy. |
| Same controller `_provider_audit_rows`, `_provider_audit_count`, `_latest_successful_resolution`, `_assert_provider_version_history`, `_assert_provider_version_revoked` | Denial, rotation, concurrent-use, revoke and abort assertions | **Remove Secrets SQLite/container-exec witnesses from operator acceptance.** Keep Secrets' owner audit/version tests. G's required policy revocation uses CPK policy command history plus exact current grant and the actual denied operation; that does not expose every provider audit/version row. Other still-required observations need an explicit owner mapping before deletion, not an invented universal audit API. |
| Same controller `_provider_write_secret`, `_provider_rotate_secret`, `_provider_revoke_secret`, `_provider_request`; corresponding remote-TLS custody helpers | Secret-provider scenario setup/rotation/denials; `cpk_server_remote_tls_secret_custody_source_live.py` deploy/deny/resume | **Replace post-bootstrap operator mutations, pending exact capability proof.** F2 policy grant/revoke is not secret-value write/rotation/revocation. The selected upstream material-provision route can be evaluated for its specific provisioning contract; it is HTTP-only and must not be advertised as a general Secrets administration API. Preserve separately authorized Secrets bootstrap and provider-owned tests. |
| `scripts/cpk_server_source_live_abort.py::compensate_abort`; secret-provider `_run_cloudflare_abort_cleanup`, `_emergency_compensate_cloudflare`, `_stop_remove_exact_failed_connector`, `_provider_revoke_exact_version` | Cloudflare smoke exit/fault path and `test_source_live_abort_compensation.py` | **Delete parallel compensation from the maintained operational path after supported replacement/explicit recovery disposition.** Successful create/current followed by approved desired-empty execution is normal removal. Partial allocation is not a successful removal premise. A denied or uncertain CPK command must stop and report; it cannot fall through to direct provider deletion. No new automatic cleanup route is implied. Historical emergency evidence remains historical. |
| `scripts/cpk_server_source_live_report.py` | `test_source_live_phase_reporting.py`; G names it as the existing bounded reporting owner | **Retain bounded reporting where reused.** It formats finite public evidence and preserves primary failures. It is not a provider authority or alternate durable history. Remove no reporting law merely because its filename says source-live. |
| `scripts/cpk_server_secret_provider_source_live_smoke.sh`, `cpk_server_cloudflare_secret_custody_source_live_smoke.sh` | Direct scenario entrances; published gateway/secret-consumers wrappers select the first; product image/bootstrap and lifecycle tests inspect them | **Replace post-bootstrap sections, pending G.** Retain only the reviewed process bootstrap, exact fixture lifecycle and explicitly admitted cleanup prerequisites needed by the established gate. Static per-workspace fixture policy, DB evidence export and legacy controller invocation cannot be the new operator example. Do not delete the sole process fixture while G is still selecting its reusable owner. |
| `scripts/cpk_server_hosted_activity_smoke.sh` and `cpk_server_workspace_a_router_transition_smoke.sh`, `cpk_server_workspace_b_multiplexer_observer_smoke.sh`, `cpk_server_workspace_c_postgres_retained_data_smoke.sh`, `cpk_server_seeded_stress_public_ingress_smoke.sh` | The four small wrappers select scenarios in the hosted shell/controller; image/bootstrap tests assert historical wiring | **Replace/remove obsolete scenario entrances with their callers after public replacements pass.** Keep genuine workload/data witnesses at the owning product boundary. Source-string assertions for retired scaffolding go with that scaffolding; do not remove unrelated tests in the large image-bootstrap module. |
| `scripts/cpk_server_recursive_activity.py` / `_smoke.sh`, `cpk_server_recursive_tls_activity.py` / `_smoke.sh`, `cpk_server_remote_tls_secret_custody_source_live.py` / `_smoke.sh` | Their respective shell entrypoints; hosted imports and image/bootstrap tests | **Pending caller-specific replacement.** Public child deployment may be retained as a thin client; direct network attachment, static grants and provider mutation cannot become the final G operator path. #163 remains downstream; no assertion that G already replaces every recursive/TLS scenario. |
| `scripts/cpk_server_gateway_published_live_smoke.sh`, `cpk_server_secret_consumers_published_live_smoke.sh` | Published-image acceptance entrances and their image/bootstrap tests | **Retain separate artifact qualification until explicitly superseded.** Rewrite obsolete controller calls only with the matching published proof. Source-built G acceptance is not immutable-image qualification. |
| `scripts/gateway_self_health_diagnostic.py`; product `gateway_self_health_diagnostic.py`, `_gateway_diagnostic_input.py`, `_gateway_diagnostic_bootstrap.py` | Script delegates `main`; product tests exercise packet/authority/transaction/signing boundary; `gateway_ingress_admission.py` also imports the input/bootstrap readers | **Delete temporary operational composition after exact self-health replacement is demonstrated.** This is private Operations authorization + signer dispatch, not a CPK HTTP client. Whole-family deletion is unsafe now: the retained-ingress inspector uses `read_file` / `bounded_json`. Resolve that consumer's disposition first. Preserve shared owner tests; remove only diagnostic-specific mirrored machinery with its retired source. |
| Product `gateway_ingress_admission.py`; `test_gateway_ingress_admission.py` | Module CLI and product tests; no other runtime importer found in the scanned repository | **Retain pending explicit read-only diagnostic disposition.** It performs four fixed Cloudflare GETs for retained #221 ingress and writes a private receipt. It is neither a CPK-owned resource-epoch read nor permission to adopt/delete retained infrastructure. Do not inspect its protected inputs in this task. |
| `scripts/cpk_local_gateway_structural_grant_check.py`, `_structural_grant_image_smoke.sh`, `_private_probe_smoke.sh` | Gateway product/image verification and relevant product tests | **Retain independent gateway contract/image testing.** Synthetic signing at the verifier's owner boundary is not automatically a parallel CPK operator executor. No G operational credit from these isolated fixtures. |
| `scripts/cpk_server_public_graph_convergence.py` / `_smoke.sh`; `products/cpk_server/src/control_plane_kit_servers_cpk_server/client/` | Public convergence/persistent-demo entrances; installed `cpk` command and its owner tests | **Retain public client and supported graph loop.** Convergence's `write_bootstrap` supplies static fixture identities; it must not be reused as routine dynamic enrollment. Thin post-bootstrap clients may submit exact public commands, poll bounded status and report public evidence, without owning policy or provider effects. |
| `bootstrap.sh`; product `bootstrap*.py`, `root_commissioning.py`, `installation.py`; `scripts/acquire_root_accounts.sh`, `inspect_root_accounts.sh`, `root_account_projection.py`, `root_artifact_*`; root fixture/image launchers | Documented root installation flow and ordinary `test.sh` bootstrap/product gates | **Retain minimum pre-CPK installer and one-time adoption responsibilities.** Starting CPK before it exists is a real boundary, not an excuse for routine workspace/policy editing or post-bootstrap bypasses. Preserve exact-owner fixture cleanup; no broad pruning. |
| `/tmp/cpk225-maintenance-artifact`, associated maintenance/inspection/controller/launcher packets and local binding proposals | Historical #225 coordination/evidence anchors; not tracked repository entrypoints | **Retain historical evidence; no filesystem disposal here.** No directory traversal, protected contents, receipts, credentials or tokens are read. Repository searches cannot prove these external artifacts are absent or unused. Their exact disposal requires a separate scoped plan. |

## Public command and evidence map

These are contracts, not permission grants or proof of a running deployment.
`W` denotes `/workspaces/{workspace_id}`. HTTP commands below use POST and
reads use GET. MCP names come from Core's accepted parity catalogue, not string
rewriting. Authentication, each owner's current admission and required explicit
plan/approval remain mandatory.

| Operator action | HTTP | MCP | Public evidence / limit |
| --- | --- | --- | --- |
| Create workspace | `/administration/workspaces` | `create_workspace_as_administrator` | Creation result; `GET W/graphs/current` / `get_current_graph`. Does not grant access. |
| Ordinary permission | `W/permissions/grant`, `W/permissions/revoke` | `grant_workspace_permissions`, `revoke_workspace_permissions` | `GET W/permissions/inspect`, `/history`; `inspect_workspace_permission`, `list_workspace_permission_history`. Full target identity and current revision. |
| Runtime management assignment | `W/runtime-management/grant`, `W/runtime-management/revoke` | `grant_managed_runtime_access`, `revoke_managed_runtime_access` | `GET W/runtime-management/inspect`, `/history`; `inspect_managed_runtime_assignment`, `list_managed_runtime_assignment_history`. Separate from ordinary permission and active runtime registration. |
| Prepare / plan | `W/deployments/prepare`, `W/plans` | `prepare_deployment`, `plan_deployment` | Owner-returned plan/operation coordinates; no local planning or invented receipts. |
| Approve / admit | `W/plans/{plan_id}/approval`, `W/approvals/{approval_id}/decision`, `W/plans/{plan_id}/admission` | `request_approval`, `decide_approval`, `admit_deployment` | Exact plan-bound approval/admission. A user task approval does not fabricate a durable server approval. |
| Claim / start / execute / advance | `W/runs/{run_id}/claim`, `/start`, `/execute`, `/advance-current-graph` | `claim_run`, `start_run`, `execute_deployment`, `advance_current_graph` | Public command results, `GET W/runs/{run_id}/events` / `list_run_events`, current graph. Stop on uncertain results; do not infer redispatch authority. |
| Ordinary gateway probe | `W/gateways/{gateway_node_id}/probes` | `request_gateway_probe` | `GET W/gateway-probes/{probe_id}` / `get_gateway_probe_detail`; timeline / `list_gateway_probes`. Do not equate this probe contract with all self-health diagnostic semantics. |
| Provision secret material | `W/secret-material/provision` | **No mutation MCP binding** | `GET W/secret-material-provisions/{request_id}` / `get_secret_material_provision`. Contract is provisioning, not arbitrary provider audit, rotation or cleanup. |

The detailed ordinary/management payload example remains
[workspace administration](implementation/workspace-administration-example.md).
For full desired graph planning/application and bounded history, use the
[public client guide](../products/cpk_server/docs/client.md). Those are existing
interfaces, not a new retirement CLI or fixture framework.

### Six provider-policy routes

Reuse [G's accepted route/evidence map](https://github.com/OpenJ92/control-plane-kit-servers/issues/342#issuecomment-6506306244).
Here `P` denotes `/administration/provider-policies/{logical_provider_id}`.

| HTTP | MCP |
| --- | --- |
| POST `P/grants` | `grant_provider_policy` |
| POST `P/grants/{grant_id}/revoke` | `revoke_provider_policy` |
| POST `P/commands/{command_id}/reconcile` | `reconcile_provider_policy` |
| GET `P/commands/{command_id}` | `get_provider_policy_command` |
| GET `P/grants/{grant_id}` | `get_provider_policy_grant` |
| GET `P/grants` | `list_provider_policy_grants` |

Grant/revoke public payloads are `coordinate`, `expected_revision`,
`idempotency_key`; the coordinate is the exact subject/workspace/action/intent.
The server selects the fixed binding after dedicated admission. Public callers
cannot supply provider endpoints, credential locations or actor authority.

The command read is local recorded intent/outcome. Exact grant reads and one
filtered list page query current provider policy. An absent list item is not an
exact revocation witness. Reconcile reads canonical evidence for the original
provider correlation and may append a local observation; it cannot redispatch.
Current state alone cannot resolve an uncertain historical command. F2 proof
requires #351, then G's actual same-process grant/revoke and denied-use evidence.

## Existing gaps and proof-dependent removal order

1. **G public ingress evidence:** the SQL epoch helper reads epoch, status,
   tunnel/DNS IDs and generated provider version; abort helpers additionally
   reconstruct exact acknowledged effects. Core's inspected route catalogue has
   no separately named ingress-resource-epoch route. This does not prove those
   facts are absent from run-event projections. Resolve the existing G field
   coverage question with the Operations projection owner before replacing SQL.
   Registration reads are not that proof. If a required fact is missing, North
   names the smallest owning prerequisite; H does not build a private reader.
2. **Distinct health/provider actions:** public gateway probes, secret material
   provisioning and F2 policy commands have different contracts. Do not rename
   them into replacements for self-health signing, secret-version mutation or
   arbitrary provider audit. Bind only actions actually required by G/H; preserve
   owner-only testing rather than expanding the public API for incidental old
   fixture observations.
3. **Uncertain/partial allocation:** normal approved desired-empty execution
   replaces successful lifecycle teardown. It does not authorize fallback
   compensation after denied admission or incomplete ownership. Preserve the
   accepted partial-allocation recovery limitation and historical uncertainty;
   separately planned recovery is not silently introduced by retirement.
4. **Source removals:** after G's evidence is linked, remove each replaced bypass
   and every active invocation together, trim only its implementation-mirroring
   tests, and update its companion. Keep existing thin client/reporting pieces
   without transplanting another controller. Recheck the diagnostic reader
   consumer before deleting shared helpers.
5. **Acceptance:** Meridian reviews inventory/removal and Kepler ownership;
   run affected owning Docker `./test.sh` checks and the existing public path as
   required. Search tracked source, scripts, examples, docs and workflows for
   active references to each removed entrypoint. Classify historical mentions
   separately. H remains open until G and these removal checks pass; no merge
   from this initial documentation checkpoint.

## Trace and verification

At the recorded Servers base, `HostedWorkflow.create_workspace` calls the old
public creation route, while `_execute_to_completion` wraps CPK execution in
host Docker network synchronization by default. The intended transformation is
administrator-led dynamic creation and a thin execution client with connectivity
supplied by reviewed product topology. `run_diagnostic` instead opens an
Operations unit of work, authorizes two secret uses, commits, signs and sends
outside the server; this is the temporary composition targeted for replacement.
`_owned_cloudflare_epoch_evidence` reads Operations SQL; abort code combines SQL
ownership reconstruction with direct provider deletion. None becomes a public
acceptance witness merely because its output is bounded.

Source anchors: `scripts/cpk_server_hosted_activity.py:485,507,2119,2164`;
`scripts/cpk_server_secret_provider_source_live.py:583,2198,2688,4276`;
product `gateway_self_health_diagnostic.py::run_diagnostic` and
`gateway_ingress_admission.py` imports. Replacement definitions are Core
`operations/http.py::operator_read_http_routes/operator_command_http_routes`
and `operations/parity.py` at the accepted upstream coordinate above.

The first checkpoint is prose-only and uses `git diff --check`. No Docker gate,
application import, provider operation, credential read, local artifact deletion,
image publication or retained-service action is claimed. Later source edits
require the unchanged repository Docker suite; stop on apparatus failure. Tests
and CI remain owner evidence, not a reason to rerun live scenarios without their
existing release boundary.
