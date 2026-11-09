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
bootstrap_runtime._material and admit_workspace_intent verify the final index.
The real credential verifier separately authenticates all three identities and
checks setup-only administration. Existing Secrets credentials reader/authorizer
verifies the fresh provider policy/token locally. No provider endpoint is called.
Completion is atomically renamed only after those owners pass; public output is
digests of public plans, role identities and file names, no raw/private hashes.
Existing/partial output holds without retry, adoption, cleanup or regeneration.

## CLI and source execution

`bootstrap.sh material-plan DRIVER INPUT COMMISSION_PLAN PUBLIC COMPLETE PUBLIC_SHA INTENT_DIGEST`
mounts only those public files read-only in a no-network/no-socket controller.
`bootstrap.sh material-prepare DRIVER PLAN DIGEST STATE` validates/creates a new
0700 parent and mounts only it plus the public plan; the leaf is created exclusively
by the preparer. CLI inside the image is root_material_preparation plan/prepare.
Driver must contain this exact reviewed source/cohort; the old cached image alone
does not contain the new production entry. Never fall back to old fixtures or
retarget a tag. No real material execution has been released by this source note.

The existing cached source-test owner now has a narrow
--root-material-preparation-source-tests selector: normal support/policy/integrity,
then seven isolated tests under exact read-only source exports. No build/pull,
network/socket/DB or real commissioning directory. Synthetic test keys exist in
memory only to obtain actual owner-rendered public records; no PEM files exist.
Public-only/stale/crossed receipt refusal, real material/identity validation,
bootstrap-vs-preparation digest and driver binding, strict modes, partial hold,
no completed-state reuse and bounded CLI output are covered. Evidence pending.

Rowan owns parent website projection separately; Lin owns the coherent installer
driver/runtime image packaging. Merge their reviewed inputs before calculating
the real root digest. Existing website/grandparent/tunnel/DNS/token/volumes are
not touched. Actual protected preparation goes to North for verification/release
within Jacob's approval; no duplicate permission request is needed.
