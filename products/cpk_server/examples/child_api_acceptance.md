# Public child installation acceptance

Governing issue: [Servers #163](https://github.com/OpenJ92/control-plane-kit-servers/issues/163).
This is the minimum parent/child journey under CPK1778. Component tests and the
ordinary root bootstrap smoke do not prove this journey.

The source recipe is `public_child_api.py`; `tests/live_child_api.py` is its
actual HTTP witness. Both use the maintained `TopologyClient` and shared
`DockerCpkInstallation`. The witness has no Docker socket, SQL connection, or
provider client. It must run inside the owning Docker-backed test invocation
under a separately reviewed one-run effect plan. The external fixture is not yet
integrated; the files below are its concrete input contract, not instructions
to run an alternate harness. No live child acceptance is currently claimed.

## Input and authority

Proposed identities, pending confirmation: parent installation `cpk163-parent`,
parent workspace `cpk163-parent-workspace`, child installation `cpk163-child`,
child workspace `cpk163-child-workspace`, hostname
`cpk163-child.openj92.dev`. The child proof runtime ID is `cpk163-child-proof`
and its network name is `cpk-cpk163-child-proof`. Conflicts require a stop;
existing installations and the retained 1752 root are not adopted or modified.

The fixture mounts one private invocation directory at `/witness`:

- `input.json`, `plan.json`, `state/receipt.json`: actual root bootstrap input,
  reviewed plan/digest and returned acquisition receipt.
- `child-input.json`: `installation` contains the shared installation fields,
  exact product documents, named ingress descriptor, runtime access descriptor,
  workspace grants and reference-only material bindings. `setup` contains
  `workspace_name`, `provider` with its admitted provider ID/prefixes/intents,
  and `secret_references` with existing `reference`/`allowed_intents` fields.
- `config/cpk/profiles/parent.json` and `child.json`: existing
  `cpk.client-profile.v1` documents, exact endpoint/workspace and private
  credential-file references for operator/approver/worker. The child endpoint
  is its real named HTTPS endpoint. Profiles and credentials must meet the
  existing client's ownership and private-mode checks.
- `child-api/`: exclusive API witness progress and existing per-client journals.
  Existing or uncertain deployment/setup progress blocks a repeated phase.
- `parent-restart/record.json`: written only by the released
  `live_root_bootstrap.py restart-for-child` fixture phase after observing the
  receipt-owned parent CPK process restart. It binds the root receipt digest,
  daemon, exact container IDs and before/after process start timestamps.

Root/child credentials grant their own workspace scopes. Setup needs workspace
create/read/edit, provider register/read, and runtime authority plus delivery
register/read. Execution separately needs plan request/approve/execute,
plan approve-destructive, execution operate and runtime-authority use. The
parent additionally needs provider use and ingress register/read/use. Use the
existing public command contracts for catalogue imports and admissions; do not
supply `actor_scopes` in requests. Docker socket access is trusted host
administration, including when delivered to the child.

Before child deployment, five child material values must actually exist in the
parent's admitted Secrets custody: control credential, PostgreSQL password,
custody root key, provider credentials document and provider client credential.
Their use intents are respectively `application.control-token`,
`postgres.password`, `secrets.custody-root-key`,
`secrets.provider-credentials-document`, and `application.control-token`.
Once-only synthetic fixture generation and initial custody writes require the
concrete effect release. Record returned versions and admissions without
values. This is fixture provisioning, not production credential generation or
post-deployment child repair.

Cloudflare account/zone IDs, exact hostname, a scoped API-token input and its
admitted reference, generated-token custody prefix and authority must be fixed
before release. Provider-registration IDs come from root setup responses.
Private image pull authority is needed if the approved execution requires it;
Docker credential-helper configuration is not treated as raw credentials.
No credential locations or values belong in a public plan or issue comment.

## Ordered witness

1. Acquire the ephemeral root through the actual `bootstrap.sh`. Complete
   initial custody provisioning and public admission before child deployment.
2. The `deploy` phase imports exact composed variants, prepares the shared child
   graph through the parent client, records the returned plan, then applies it
   only within the explicitly released effect envelope. Initial preparation
   uses the existing direct-file path; teardown below uses saved revisions.
3. Before initialization, public status/current/plan evidence must converge.
   The existing validated client journal binds the original canonical desired
   bytes digest, endpoint/workspace and returned graph/projection/plan IDs to
   that result. Public graph descriptors are redacted; matching node names
   alone is insufficient.
4. Initialize the child through its actual authenticated HTTPS API. Verify
   wrong-credential denial on that endpoint; a TLS/connection failure does not
   count as denial. Prepare a child runtime with a real `start-runtime` action,
   approve its exact plan separately, execute, and verify public current truth.
5. Only after phase `deployed`, restart the exact receipt-owned parent CPK
   process. Preserve PostgreSQL, Secrets, the root receipt and all child
   resources. `reconnect` requires observed restart evidence plus the same
   public parent session/plan/run/event history and current projection, and
   verifies the child remains usable. History reporting is bounded; retained
   truncation is explicit and never presented as an exhaustive event export.
6. The `teardown` phase first removes the child proof runtime through the child
   API. Save an EMPTY desired catalogue revision, select it, read back the
   exact empty graph and selected latest revision, then prepare that
   `SavedDesiredRevision`, inspect/approve its destructive plan and apply.
7. Repeat that sequence through the parent API to remove the child installation.
   Verify current/desired empty graph IDs and plan/run/history correlation.
   No direct-file empty shortcut or direct Docker child teardown counts.
8. Separately reconcile ingress removal and retained resources from actual
   effect ownership evidence. Empty graph convergence does not mean retained
   PostgreSQL data, Secrets custody or protected file volumes were deleted.
   Exact approved retained-resource cleanup, provider absence checks and root
   receipt cleanup follow successful API teardown; they remain fixture work
   to complete before live release.

## Stops and evidence

Transport ambiguity or mismatched identities stop the chain. Preserve pending
intent, public client journals, known returned IDs and a bounded fixed failure;
never blindly rerun, reset, adopt, rekey or manually repair the child. Preserve
retained state unless its exact deletion is approved. No broad prune or
unbounded provider inventory is part of this recipe.

Before execution, the durable issue must name the reviewed source/driver and
canonical images, real account/zone/hostname, initial custody and authority
inputs, exact restart, retention/deletion disposition and cleanup evidence.
The source checkpoint is not an external-effect release or acceptance result.
