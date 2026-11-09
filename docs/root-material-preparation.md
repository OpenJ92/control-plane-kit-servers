# Offline root material preparation

Source implementation checkpoint; not yet executed or accepted. This command
does not start services, use a provider token, install a database or allocate
ingress. Public startup/child execution remain separate approved plans.

Existing entry points remain: root_commissioning prepares only receiving read
trust; bootstrap plan/apply consumes the existing root material.v2 index. New
material-plan/material-prepare fill the missing protected-input writer without
new Operations state, stores, authentication formats or bootstrap schemas.

## Public input and pure plan

The new cpk.root-material.intent.v1 contains bootstrap_input (the existing complete
root input, prior to dynamic authority commitment), principals with exact human,
setup and worker identities, permissions per role, capabilities, optional
management {runtime_id,authority_ref,capability_id}, scoped provider_grants and
custody {host_directory,uid,gid}. Setup alone is administrator; human/setup are
operator identities and worker is a worker identity. All use the existing static
development issuer and multi-principal verifier. Permission values are existing
PolicyScope values, not a blanket generated grant.

Plan also receives ONLY the approved commissioning plan, exact public.json bytes,
complete.json and pinned intent/public digests. Verify both receipt digests,
both distinct receiver IDs, actual decoded role targets and public verifiers.
The bootstrap CPK/Secrets docs must carry those exact artifact values. No PEM
path or containing commissioning directory is mounted/read; _reuse is not used.
The new output parent must neither contain nor live inside that read-trust
directory. Real preparation shell requires a fresh private parent and fresh leaf.

Pure projection creates the existing workspace-policy commitment and exact
plan_root_bootstrap output with the intended installer DRIVER image. That driver
is separate from the runtime CPK product image and the earlier commissioning
preparer. The preparation plan pins both its own digest and the actual bootstrap
digest. No ID, token, password, key or private file is allocated by planning.
Unfrozen launch images, receiving/sender documents or ports prevent a real
preparation plan/release; design and synthetic tests do not fill them in.

## Fresh protected prepare

Recompute the full projection/driver/digests before allocation. Create an exclusive
0700 output, persist an incomplete marker and directory before generation. Produce
three independent bearer values, PG password, Secrets custody key and provider
client token; existing principal/provider JSON refers to those values. Setup
uses the existing control_credential reference. Material.v2.files is exactly the
owner-required reference set; human/worker bearer files are private handoff
locators outside that reference index. Nothing reads or reuses old credentials.

Secret files/index/policy/plan outputs are0400; intent/completion0600; all generated
files are exclusively created without following links and fsynced. Existing
bootstrap_runtime._material_document and admit_workspace_intent verify the
in-memory index and its protected siblings. Ordinary _material shares that same
validator after reading an existing index. No pending index file is written:
neither apply nor initialization inspection can consume an incomplete index under
an alternate name. Existing arbitrary legacy index names keep their behavior.
The real credential verifier separately authenticates all three identities and
checks setup-only administration. The pinned Secrets158b17ed credentials reader
and authorizer authenticate the fresh token; exact decoded typed grants and empty
capabilities must match the plan. Its package-private provider_policy._canonical_seed
also validates the initial policy during pure planning and again on decoded
credentials. This reuses the actual seed owner's action/intent vocabulary without
database initialization. It proves prepared initial policy, not durable grants or
request-time authorization. No provider endpoint is called.
Completion is atomically renamed only after those owners pass, then the canonical
index is written/fsynced as index.new, atomically renamed to index.json and the
directory fsynced. Only already validated material can exist under that temporary
name. Completion without a canonical index is
incomplete and holds on re-entry without regeneration; public output is
digests of public plans, role identities and file names, no raw/private hashes.
Existing/partial output holds without retry, adoption, cleanup or regeneration.

## CLI and source execution

`bootstrap.sh material-plan DRIVER INPUT COMMISSION_PLAN PUBLIC COMPLETE PUBLIC_SHA INTENT_DIGEST`
mounts only those public files read-only in a no-network/no-socket controller.
`bootstrap.sh material-prepare DRIVER PLAN DIGEST STATE` first runs read-only
plan/digest/driver/destination/UID/GID verification, before creating the new
0700 parent. It then mounts only that parent plus the public plan; the leaf is created exclusively
by the preparer. CLI inside the image is root_material_preparation plan/prepare.
Driver must contain this exact reviewed source/cohort; the old cached image alone
does not contain the new production entry. Never fall back to old fixtures or
retarget a tag. No real material execution has been released by this source note.

The existing cached source-test owner now has a narrow
--root-material-preparation-source-tests selector: normal support/policy/integrity,
then eleven preparation tests and the two existing legacy material/redaction and
uncertain-receipt regressions under exact read-only source exports. No build/pull,
network/socket/DB or real commissioning directory. Synthetic test keys exist in
memory only to obtain actual owner-rendered public records; no PEM files exist.
Public-only/stale/crossed receipt refusal, real material/identity validation,
bootstrap-vs-preparation digest and driver binding, strict modes, partial hold,
no completed-state reuse and bounded CLI output are covered. The real shell's
negative cases each use their own call ledger; the valid control uses an independent
fresh destination and plan. Its executable Docker fixture stays on private
container tmpfs and delegates real verification, then stops at a prepare sentinel.
The prior red and diagnostic failures remain recorded on #384; corrected evidence
is pending. Temporary stage-diagnostic wrappers are removed from the corrected tests.

Rowan owns parent website projection separately; Lin owns the coherent installer
driver/runtime image packaging. Merge their reviewed inputs before calculating
the real root digest. Existing website/grandparent/tunnel/DNS/token/volumes are
not touched. Actual protected preparation goes to North for verification/release
within Jacob's approval; no duplicate permission request is needed.

## Optional fixed two-workspace provider policy

Default input, digest and twelve-file output inventory retain the db74 behavior.
An explicit provider_policy object opts into a separate reviewed authority shape:
child_workspace_id, cpk_grants, external_provisioner_subject and
external_provisioner_grants. It does not change human/setup/worker scopes.

The ordinary provider subject remains root-<installation_id>. Its original parent
resolve seed must be retained; optional-mode parent intents are limited to
postgres.password, application.control-token and cloudflare.tunnel-token resolve.
Only one distinct named child workspace is allowed. There, write/resolve is limited
to four ordinary graph materials, Cloudflare API/tunnel tokens, and five explicit
signer import intents. Child-only secret.metadata uses an empty intent list and
is required for immutable-version selection. Duplicate seed coordinates refuse.
No third workspace, wildcard, provider administration, generation or revocation
is admitted by this mode.

The second provider subject is distinct and has exactly one parent-workspace
secret.write/cloudflare.tunnel-token row. Its fresh external-provisioner.token is
0400 in private custody, outside the CPK runtime credential registry, reference
index and all login/worker surfaces. It differs from the ordinary provider token
and all three control bearers. Actual decoded credentials must match both planned
subjects/grants with empty capabilities before index publication.

Provider grants are workspace/action/intent authority, not exact-reference rights.
The reviewed sample policy has five rows and27 unique coordinates, with exact
references further bounded by CPK registrations and approved operator actions.
The ordinary CPK provider identity owns child runtime tunnel-token custody and
delivery; the distinct external identity writes the parent's two returned tokens.
The CPK worker is a correlated actor, not the Secrets authentication subject.

Secrets57e4fc61d6931ef078550f98154a585bda61987b is the selected owner for this
optional vocabulary, including explicit HTTP-signer write/import and resolve;
Secrets158 rejects those two intents. Do not grant native generation for them.
The established source gate can take two additional args (exact Secrets checkout
and revision), exporting that source ahead of the cached package and checking its
actual import root. The no-option gate still runs without that export.

CPK secret-material.provision currently supports only Cloudflare API tokens and
OCI pull credentials. Other ordinary/key imports require separately approved
bounded authenticated Secrets writes, then normal CPK reference/key registration
and immutable graph selection; no generic CPK import route is invented here.
The optional source capability does not apply an expanded manifest. Jacob must
review the actual additional authority before the extra bearer or broader seed
is generated. Parent provider/installer images require separate qualification;
the accepted child receiving image stays distinct.
