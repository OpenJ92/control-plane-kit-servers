## #344 / #345 implementation plan — reviewed private intent contract

This first section preserves the #345 design at its stated source coordinates.
The historical #347 continuation and launcher plan appear below; their pending
and intermediate release statements describe their named checkpoints, not the
current implementation or authority.

Current disposition: the complete #345/#346/#347 composition at
`8bb96f9d60502e44e52b2f32c2f62e345cc91b3e` passed the full owning
[run40818456065](https://github.com/OpenJ92/control-plane-kit-servers/actions/runs/40818456065)
and [independent combined review](https://github.com/OpenJ92/control-plane-kit-servers/issues/347#issuecomment-6488312730).
The intermediate dynamic-apply guard is removed. The exact current pair and
producer, accepted aligned cohort, restart/revocation/initialization and cleanup
evidence are recorded in [current artifact qualification](../current-root-artifacts.md).
Normal PR integration/checks remain separate from this checkpoint acceptance.
CPK #2040, retained lifecycle/upgrade #342, retirement #340 and live/browser #225
remain separate downstream boundaries. Nothing in this historical plan releases
provider mutations, new publication or live deployment.

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

### Authoring example for the #345 source boundary

Start with an existing valid static root input and reviewed public setup. Keep
its selected products, credential references and host binding. Change
`installation.workspace_grants` to `[]`, add the two-field
`setup.administration` summary, and prepare the exact protected policy and
administration objects shown above. The pure
`bootstrap_workspace.workspace_intent_commitment` helper accepts `policy_bytes`,
`installer`, `initialization_idempotency_key`, `public_setup`, and `administration`;
put its result in `installation.workspace_authority.private_intent_sha256` with
`mode: dynamic-v1`. It performs no file reads or authority decision.

Call the existing pure `plan_root_bootstrap` with the reviewed driver image.
Only after that plan is reviewed, bind its `digest` in the private v2 material
index. Use safe sibling names and owner-only file permissions for all private
material, including the policy. Single-operator mode must name the existing
fixed verifier identity; multi-principal mode uses the existing private principal
document and explicit separate setup bearer. Synthetic examples are shapes,
never default identities, credentials or granted access.

At the #345 intermediate boundary, applying this valid input returns
`dynamic-bootstrap-incomplete` before Docker. That is expected: this example
qualifies authoring and private admission, not a usable root deployment.

## Historical #347 current-artifact launcher plan at25bf669a

Planning source is Servers `25bf669a8234993177112a001bb5c61eb0443f46`, tree
`ee55410c9495394d57392b90d2fae7ef86b39466`. Selected Operations is
`a487fc0ed9b9c821256e4f4c065dd6bc6312331f`; Core `4cc1716`, SDK `464df26`,
Interpreters `bd08b931` and Secrets `067678f` retain the canonical full coordinates.
Reuse the #347 route/input traces and independent source/component dispositions
on its governing issue. The local changed path passed 1,138 package and 26 support
tests plus actual initialization/public HTTP/PostgreSQL composition. A later
unchanged literal Docker-endpoint guard stopped that local owning gate. Existing
GitHub run40724897642 subsequently passed at this exact checkpoint, including
later image/receiver stages, historical root cleanup and the final residue audit.
Meridian independently confirmed SOURCE-BUILT OWNING GATE PASS. The
[terminal receipt](https://github.com/OpenJ92/control-plane-kit-servers/issues/347#issuecomment-6474938152)
records its scope; current-image dynamic launcher qualification remains open.

### Selected behavior and remaining connection

`bootstrap_cli.public_setup` now re-admits the fixed private files before transport
or readiness, maps actual administration/permission/management results and reads,
and accepts the owner's legitimate null desired pointer. `bootstrap_runtime`
stages the minimized public-helper files and decodes their bounded progress.
The initializer remains a separate database owner composition. Normal process
construction consumes its retained binding and never invokes either helper.
The full public apply guard is still present.

`test.sh` currently qualifies an optional immutable CPK/Secrets pair through the
existing artifact smoke owners, then runs the historical static root fixture.
`live_root_bootstrap.prepare` builds its public input from canonical historical
descriptors and adds an inert configuration witness. `check` uses a CPK account
baseline sealed for that historical digest. Neither this path nor the new
in-process component proves a fresh current-image dynamic root.

The smallest remaining connection is an additional case in these existing owners,
using the qualified pair and actual commissioning/runtime-contract factories.
No new runner, registry, owner API, deployment shortcut or artifact-admission
format is proposed.

### Bounded source delta and expected evidence

1. Extend the existing root invocation in `test.sh` with one dynamic case only
   when the already supported `published-digest` tuple is complete and admitted.
   Retain the historical static invocation and default source stages. Use the
   selected CPK digest for the driver base and the two exact repository digests
   in the authored products. Keep native PostgreSQL, fixed Hello/gateway inputs,
   canonical catalogue pins, Linux daemon guard and existing timeout unchanged.
2. Extend `live_root_bootstrap.prepare` using the actual
   `root_commissioning.plan_root_commissioning` / `prepare_root_commissioning`
   and CPK/Secrets source-runtime-contract factories already exercised by
   `root_complete_fixtures`. The dynamic case has the existing three root nodes;
   it does not add the optional website. Keep commissioning fixture custody
   private and owned. Author an explicit administrator, known targets, capability,
   setup bearer and ordinary grant intent; bind exact private bytes and the actual
   driver/plan digest with the existing v2 index. No fabricated registration ID.
3. Exercise ordinary `bootstrap.sh plan/apply` and its existing protected
   staging, initialization and authenticated public helper. Never call `_acquire`
   directly to get past the guard. Verify initialization acknowledgement before
   public setup, exact enrollment readbacks, bounded receipt progress and absence
   of completed temporary helper resources. Extend existing complete mount checks
   to include retained `installer_files`; verify the actual numeric recipient
   can read the exact private policy but cannot write it, without emitting bytes
   or identities. Preserve installer policy and database through helper cleanup.
4. Review an independent account baseline for the exact new CPK image, then add
   it to the existing `ImageAccountBaseline` witness while retaining the old row.
   Bind final-filesystem passwd/group evidence to that repository digest and its
   manifest/config/execution correspondence. Keep these identities distinct;
   manifest-valued Docker IDs are not config digests. Expected UID, primary GID
   and complete supplementary groups must come from reviewed image evidence,
   never the process being tested. Unknown tuple/baseline refuses before
   acquisition. Existing PID1 UID and installed provenance checks still apply.
5. Through actual authenticated public client calls, read enrollment, revoke the
   fixture's ordinary permission and management assignment, then restart only
   the exact owned CPK process/container. Re-read policy binding and revoked
   revisions, and prove ordinary access remains denied. Retain exact policy mount
   custody across restart; do not call initialization/setup or use direct stores
   to seed expected state. This restart is a fixture observation, not a product
   recovery API or authority to restart a retained user installation.
6. Keep completion and cleanup evidence separate. Preserve existing pending
   stop/no-redispatch, exact-ID/label cleanup and final residue audit. An uncertain
   acquisition holds cleanup under the existing rule. Add no compensation,
   image deletion, broad prune, service repair or automatic retry. Retain borrowed
   published images. The gate must record both producer and gate source, exact
   tuple, actual reached boundaries and remaining unknowns.

The full apply guard changes only in the independently reviewed integrated source
delta released for the qualified tuple's ordinary launcher gate. Keep invalid
private-input/prior-receipt targets; replace only the intermediate valid-input
incomplete-path expectation with the newly supported public boundary. Guard
removal cannot substitute for actual successful evidence. Until that gate passes,
#347/#344 and the shared PR remain unaccepted, even if normal source CI is green.

### Producer and gate sequencing

The initial common producer proposal was source-gate-qualified `25bf669a`.
It is superseded by the accepted #349 cohort integration described below and
must not be published for the combined gate. Both products
use the existing `publish-product-image.yml` / `publish_product_image.sh` path,
which builds Linux/amd64 and records numeric user, source label, execution ID and
actual repository digest. Concrete destinations, proposed unused tags and recipe
hashes belong in the #347 proposal. No publication is authorized by this plan.

After publication, review the actual immutable tuple and independent CPK account
evidence before adding its baseline. The final launcher gate source cannot yet
be named: it must include the reviewed actual-image account baseline. Compare
the candidate producer with that exact final revision across coordinates,
recipes, copied source and entrypoints. In particular, the external driver's
Dockerfile copies current bootstrap modules over its CPK base; that selected
driver source must be identified separately from the ordinary server process.
Any runtime-affecting change requires an explicit equivalence disposition or a
new reviewed producer coordinate. Do not infer adoption from labels or a source
pin. Use one existing optional-tuple owning run for the finished boundary when
released, not an extra framework or an unreviewed intermediate deployment.

The documentation delta teaches these currently available source contracts and
their limitations. Planning/Markdown verification requires `git diff --check`;
new executable fixture/guard changes require independent review and the owning
Docker gate. Publication, current-artifact qualification, live #225 and G/#342
remain distinct permissions and acceptance boundaries.

### Integrated source candidate after authoring review

Meridian passed the bounded authored-input checkpoint988b9aa, explicitly noting
that its original target reconstructed material after authoring. The subsequent
candidate reuses `workspace_intent_commitment` and adds an actual prepare-writer
to admission target. It wires the additional optional-tuple shell invocation,
actual helper absence/PID1/private policy custody, public revocation, owned
container restart, retained initialization inspection and exact cleanup. It also
removes the intermediate public apply guard in that same candidate. Corrected
source `5c495895` passed independent source review and the complete default gate.
The later offline account projection source `ac144857` also passed independent
review and default gate 40738175098, including seven synthetic projection laws.
Neither default run selected a current pair or establishes a usable deployment.

At that checkpoint the current-image account seal and final gate revision were
unresolved. Only the historical account row existed; new references refused
before acquisition. The current disposition at the top supersedes those gaps.
No image publication or inspection is implied by preparing the source candidate.

### Reconciliation after accepted #349 first merge

PR #350 merged first as `fc4cd5b3379b2d38dd06319a997f7ad894dfcca8` into the same
roadmap destination. The combined #348 source retains that accepted aligned
cohort and Components HTTP/MCP witness alongside #346 initialization and #347
authenticated setup. Core/Operations `fec0816281aeb83ede98616adcc4f96dfe5777a8`
descends from the earlier selected `a487fc0`; its schema installer, initialization,
permission and management owners are unchanged. Its server dispatcher adds the
product list/detail read routes without changing the administration decoder.
The existing `server.py::create_app` installs those owner routes. The receiver
fixture runs initialization, setup and then workspace authority, whose restarted
factory invokes `components_acceptance` against the same owning PostgreSQL suite.

Conflict resolution retains #349 coordinate/recipe/provenance values and both
branches' fixture composition. No permission, initializer, public setup or
Components algorithm is reimplemented. Existing source evidence remains tied to
its original tree; the combined source needs independent review and the unchanged
owning Docker gate. The old producer/recipe equivalence no longer applies. Use
the reviewed and source-tested combined commit for a refreshed publication packet;
actual publication, account inspection, current-pair qualification and live
deployment remain separately released effects.
## Current #351 dependency selection

#351 advances this source's existing dependency/provenance surface through
`coordinates/server-products.json`: Core/Operations 7afef43, SDK 220f631,
Secrets a3ca963, Interpreters 71ab335. These are actual accepted owner merges.
The canonical manifest carries full commits. Existing extras, runner, provenance
predicates and published product/image/catalogue identities are preserved.
Earlier cohort accounts below are historical. This checkpoint awaits the owning
Servers gate; pin selection alone is not installed or live acceptance.
