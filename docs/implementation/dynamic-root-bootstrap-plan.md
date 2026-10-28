## #344 / #345 implementation plan — reviewed private intent contract

Vale implements; Meridian reviews independently; North owns scope, releases and merge. Repository `OpenJ92/control-plane-kit-servers`, branch `codex/344-dynamic-root-bootstrap`. Base is the independently verified #343 merge `71e058024bc5c6557b13ba86120554945c4a32fa`, tree `45796b19b719b9a9485c61de5266c02463657b85`; destination `roadmap/1813-runtime-control`. One coherent #344 PR will carry ordered independently reviewed #345 → #346 → #347 slices. The selected Core/Operations/Interpreters/SDK/Secrets cohort is unchanged from #341. Meridian returned PLAN PASS for the revised private-intent contract; North released the docs/target checkpoint, shared draft PR and bounded implementation. No executable validation is claimed by this plan.

### Existing computation and smallest missing connection

At this base, `bootstrap.py::_installation` decodes the closed public input into `DockerCpkInstallation`; `plan_root_bootstrap` composes and validates the graph, embeds the whole public input, and projects each ordinary configuration artifact's complete content into the plan. `verified_plan` recompiles and checks equality plus the reviewed digest before acquisition. Policy must not enter that ordinary artifact channel.

`bootstrap_runtime.py::_material` reads the existing private material index and sibling regular/private files before Docker construction. It binds names/references, but currently does not bind exact workspace-policy bytes, an explicit initialization actor/key or their correspondence with a reviewed setup intent. `acquire_root` preserves the prior-receipt stop. `_acquire` resolves existing credentials, then constructs Docker; its `file_volume` already owns numeric UID staging, mode 0400, content verification and pending/observed receipt boundaries. The recipient's complete mount set is checked before start. Reuse those owners; add no generic material or receipt framework.

`installation.py::_cpk_variant` currently emits static authentication and health v1. `_managed_health_artifact` and `managed_health_configuration.py::_managed_health_configuration_from_artifact` deliberately refuse v2. `_workspace_grants_json` requires nonempty static grants. `server.py::from_environment` already supports dynamic workspace files and health v2; its policy constructors, real verifier and post-receipt factory are accepted. `bootstrap_cli.py::public_setup` still creates a legacy workspace, then registrations, with one-send mutation checkpoints. Fresh initialization and revised setup remain #346/#347.

Core `ProductInstanceConfiguration.from_contract` refuses unfulfilled `configuration_requirements`; that is a public-artifact slot, not an installer-private file abstraction. Do not weaken it or invent a new Core delivery concept. Declare the private requirement in this product's existing `bootstrap.contract.json` and the root installer's explicit delivery projection. An ordinary graph alone still does not supply that installer capability, and no general-runtime policy-delivery claim is made.

Governing tests read: `test_managed_health_installation.py` (pure projection, exact bytes and fixed slots, collisions, disabled import isolation); `test_root_bootstrap_configuration.py` (plan drift, occupancy, numeric readability, unknown staging and missing mount); `test_installation_control_auth.py` (reference-only authentication, actual verifier identity/kind, setup bearer retained separately); `test_root_bootstrap.py` (prior receipt/unknown outcomes); accepted process tests and public PostgreSQL fixture from #341. Existing laws remain in their owners.

### Proposed exact input and binding shapes

Preserve absence/default static input and output unchanged. Add one optional closed public installation field:

```json
"workspace_authority": {
  "mode": "dynamic-v1",
  "private_intent_sha256": "<64 lowercase hex characters>"
}
```

Use an installation-local typed value for this descriptor, not `SecretReference`. It denotes one fixed private policy requirement, not an arbitrary path or provider reference. Dynamic installation uses explicit `workspace_grants: []`; initial durable grants are separately approved setup commands. Static mode keeps its existing nonempty-grant requirement. Single/multi credential formats remain unchanged.

The existing private material index gains a closed dynamic-only v2 arm; static continues to accept exactly v1:

```json
{
  "schema": "cpk.root-bootstrap.material.v2",
  "files": {"<existing required credential reference>": "<private sibling filename>"},
  "dynamic_workspace": {
    "plan_digest": "<exact reviewed public plan digest>",
    "policy": {"file": "workspace-policy.json", "sha256": "<exact UTF-8 byte digest>"},
    "installer": {"issuer": "<verified issuer>", "subject_id": "<explicit subject>", "kind": "operator"},
    "initialization_idempotency_key": "<explicit owner key>",
    "administration": {
      "workspace_creation_idempotency_key": "<explicit public-command key>",
      "permission_grants": [
        {"target": {"issuer": "<issuer>", "subject_id": "<subject>", "kind": "operator"},
         "scopes": ["instance:workspace:read"], "expected_revision": 0,
         "idempotency_key": "<explicit grant key>"}
      ],
      "management_grant": null
    }
  }
}
```

The referenced policy file contains only the accepted `cpk-server.workspace-authority.v1` document. Reuse `private_read`, the bounded policy decoder and owner policy/identity/key constructors. Do not add credentials, live grants or provider endpoints to policy. Reject malformed/unknown/duplicate/nonfinite input, unsafe sibling names, incorrect file permissions and oversize input using existing closed redacted errors.

Compute the public `private_intent_sha256` over canonical bytes of precisely:

```json
{
  "policy_sha256": "<exact policy bytes digest>",
  "installer": {"issuer": "<verified issuer>", "subject_id": "<explicit subject>", "kind": "operator"},
  "initialization_idempotency_key": "<explicit owner key>",
  "setup_sha256": "<canonical digest of {public_setup: complete public setup input, administration: exact private administration intent}>"
}
```

The existing plan digest already binds installation identity, selected products/images/driver, authentication references, public setup and this commitment. The private index then binds its `plan_digest` to that result. There is no circular hash: the commitment excludes `plan_digest`. Changing the policy, actor/key, setup, public input or driver requires a new corresponding reviewed plan; renaming a private file cannot substitute different bytes. The digest proves correspondence, not authority. A pure preparation helper can compute this commitment from supplied values without file/network effects; no separate binding file, signature service or approval ledger is introduced.

For concrete downstream #346/#347 contracts, **all exact administration intent stays in the protected index**, as shown above. It contains an explicit workspace-create key, at most 32 exact permission-grant requests (`target`, `scopes`, `expected_revision`, `idempotency_key`) for the installation workspace, and an optional management request (`runtime_id`, `authority_ref`, `capability_id`, `expected_revision`, `idempotency_key`, literal `registration_from: "command.runtime-authority.register"`). Reuse the selected owner request/identity/scope/key validation. There is no supplied registration ID. Child #347 consumes the actual returned registration before the management grant. No grant or initialization executes in #345.

Use the actual verified principal with `WorkspaceAdministrationPolicy.authorize`, then its `require_known` check for grant targets. A complete `GrantWorkspacePermissions` value can be validated now without effects. A `GrantManagedRuntimeAccess` cannot be constructed until its real registration ID exists: validate only the supported pre-registration intent fields here, and let #347 construct/send the actual owner command after registration. Never invent a placeholder registration ID just to pass a constructor.

The public `setup` gains only this dynamic structural summary:

```json
"administration": {"permission_grant_count": 1, "management_grant": false}
```

`permission_grant_count` is an exact integer from 1 through 32, excluding booleans; `management_grant` is a boolean. Those two fields let the pure planner derive the exact known route sequence without revealing targets, scopes, command keys or management coordinates. At private admission the count and optional-management presence must match the protected intent exactly; the existing commitment binds its complete contents. A different target or scope with an unchanged count still changes the commitment and is refused. There is no caller-supplied arbitrary route list or identity-reference language.

An authorized installer reviews the exact protected policy, initializer and administration requests alongside the public plan; ordinary emitted plans/artifacts/reports contain only the structural summary and commitment. Public commands will carry their exact authenticated payloads when #347 executes them, but that does not justify copying those payloads into the bootstrap plan or progress reports. This supersedes the initial proposal to include full grant targets in public setup input. Credential references and preexisting public setup fields retain their existing contract; no broader public disclosure is added.

### Admission before acquisition

After the prior-receipt check and before Docker construction, admit the dynamic private input once: verify exact plan/commitment/policy bytes, matching installation and whole managed-health capability catalogue, explicit installer membership in the existing administration policy, and all named setup targets/capabilities against that policy. Consume those admitted bytes for staging; do not reopen a mutable filename later.

Resolve the selected setup bearer through the actual process authentication parser/verifier using the compiled authentication inputs and already validated workspace policy. The authenticated complete identity must equal the explicit installer and be an administrator. Single mode therefore uses its existing fixed `local-development-operator` identity; it does not gain a new subject field. Multi mode consumes the existing private principal document and verifies the actual selected bearer. Never select the first policy administrator or use a declared identity as authentication. Static credential grants do not supply durable permissions. Missing/mismatched input fails before Docker I/O without a credential-bearing exception context. Keep the admitted dynamic context separate from the existing credential-reference map, with private values excluded from repr and all public projections. Children #346/#347 receive only the necessary validated protected context through existing owned helper-file machinery; no private payload is copied into the acquisition or public setup progress report.

### Delivery and process declaration

Add a CPK-node-only `installer_files` plan entry with fixed role `workspace-authority`, schema `cpk-server.workspace-authority.v1`, destination `/etc/cpk/cpk-server/workspace-authority.json`, deterministic owned volume name and retained installation lifetime. It carries no policy bytes, identity roster, private filename or private binding document. Emit `CPK_WORKSPACE_AUTHORITY=dynamic-v1` plus the fixed file path. Reject collisions with existing public environment, configuration slots, secret destinations and retained mounts.

The bootstrap contract declares this separate installer-private file and mode; it must not call it a public configuration artifact or imply ordinary graph delivery. The root executor reuses existing protected staging and read-only file subpath mounting, includes the volume in occupancy/ownership and recipient mount verification, and records only safe UID/mode/verified evidence. Keep it for CPK restarts; never include it in disposable setup/initialization-helper cleanup.

Dynamic managed-health artifact admission is enabled only alongside this explicit dynamic installation capability. Preserve the old public artifact helper's v1 default/refusal in unsupported contexts. Validate the new v2 artifact using the existing decoder plus fixed slot/Core byte bounds; emit `docker-unix-v2`, retain exact bytes and reject mixed modes. Dynamic authority without health remains legal. Policy matching occurs at private admission before effects. No runtime selection/UoW/permission logic is added to the installer.

### Child boundary and evidence

Keep dynamic root apply explicitly unavailable before any Docker acquisition until #346 initialization and #347 public setup are composed and independently reviewed. The intermediate #345 source is an authored/delivery contract, not a usable installation. The parent integrated fixture later exercises the supported full entrypoint. The owning protected-file fixture can qualify the reused production staging/decoder boundary without pretending that direct fixture staging is full bootstrap acceptance. Do not add a new simulator or expose a private deployment shortcut to get around the incomplete-path stop.

Focused targets cover: unchanged static plans; closed dynamic shape and exact private binding/drift; no policy/binding/credential material in public plans/errors; actual single/multi bearer-to-admin mapping before Docker; mode/catalogue/reserved-path refusal; retained policy ownership/mounts and numeric file/decoder composition; explicit incomplete-path refusal. Existing owner tests retain permission, initialization and idempotency semantics. Existing process tests preserve v1 refusal except at the specifically supported entrance. Update the product bootstrap contract, narrow companions and safe examples. No Core/Operations/Interpreter changes, dependency pins, schema mutation, live/provider/image effects or website work.

### Coordinator dispositions and review checkpoints

1. North chose protected exact administration intent and only a bounded public summary/commitment. The revised concrete shapes above implement that disposition. Meridian's PLAN PASS covers the minimal material-index/digest extension, exact private/public correspondence and installer-only file obligation. Source and test evidence are still required.
2. North authorized a reviewed docs/target checkpoint and **one** shared draft PR before production implementation. Put the concrete reviewed plan in that PR. Let ordinary automatic PR checks run; no manual duplicate, suppression or check bypass.
3. The previous local Docker prerequisite stop remains unresolved (required `/var/run/docker.sock` versus the host Docker Desktop socket). North explicitly retains the hold: no repair, retry, host Python or alternate runner. Use established Linux `tests.yml`/`./test.sh` for executable validation. Ordered child source/test review remains required, but do not require a ceremonial full red and green run per child. Use causal red where needed, distinguish intended missing behavior from apparatus/fixture defects, and use actual automatically triggered owning evidence. Final parent acceptance requires an unchanged complete green gate; failed checks cannot be accepted. New architecture/data boundaries still stop for review.

Next boundary: the reviewed docs/target checkpoint and shared draft PR before production implementation within the released #345 ceiling. The initial public-entrypoint targets name `dynamic-bootstrap-incomplete` as the bounded diagnostic reason for valid admitted input whose later initialization/setup path is unavailable; invalid private admission retains `material-refused`, and prior acquisition retains `prior-acquisition`. Later source review must also verify admitted-byte staging, numeric ownership and exact mounts. This plan is source-only and not authority to run initialization, acquire live resources or deploy.
