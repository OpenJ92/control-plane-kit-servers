# Servers156 source checkpoint

Governing issue: [Servers156](https://github.com/OpenJ92/control-plane-kit-servers/issues/156).
Parent acceptance: [CPK1779](https://github.com/OpenJ92/control-plane-kit/issues/1779).
Base: `3e03130eba8dd34b8adefa3b470855ec415857d1` on
`roadmap/1754-application-readiness`; feature branch `codex/156-root-docker-bootstrap`.

## Decision log

- Chosen shape: one pure projection/API module, one root acquisition/receipt
  module, one CLI/public HTTP setup module. `bootstrap.sh` only launches an
  explicitly selected Docker driver. A product-owned Dockerfile packages the
  driver on the accepted CPK image; graph products keep their canonical images.
- Why: the external root needs a process before Operations exists. Existing
  `DockerCpkInstallation`, graph codecs, secret resolver, Docker SDK, and public
  client transport already own the component languages and effects.
- Alternatives rejected: Compose; copied child effect hashes; fabricated
  Operations run provenance; private SQL initialization; source-image substitution;
  implicit host credential copying; automatic recovery or adoption.
- Important shape:

  ```python
  graph = compile_topology(compose_docker_cpk_installation(installation))
  plan = plan_root_bootstrap(document, driver_image_id=driver)
  apply_root_bootstrap(plan, expected_digest=plan["digest"], driver_image_id=driver,
                       index_path=index, state_directory=state)
  ```

  Apply recomputes the complete pure projection. Acquisition writes pending intent
  before each effect and keeps ambiguity visible. Public setup consumes the
  provider's returned registration ID and verifies available public detail reads;
  imported product references are compared with the selected descriptor digest.
- Tests: three frozen new-law tests at
  `ce2fd410b3e00b69e4f79670d4f33675bfffb2b3` cover exact shared graph/reference
  parity and projection/driver refusal, private material refusal before effects,
  and pending receipt HOLD without rewrite. The single owning red run produced
  exactly those three intended missing-module failures, with existing CPK205
  tests green; log SHA256
  `5c162d607531a8d7897903f74f767fe7e35c26920859998760a26be9b639cf05`.
  The added live witness invokes the real launcher using canonical images, checks
  public setup/readback, numeric read-only delivery, wrong-credential refusal,
  immutable completed-receipt refusal, and exact owned resource cleanup.
- Current evidence: **source checkpoint only; green not run**. Independent static
  review must pass before the single owning `./test.sh` green run. No success is
  inferred from source inspection or from image prerequisite158's earlier tests.
- Handoff: the next child uses public CPK topology/Operations workflows to deploy
  and track child installations. Root acquisition is not child tracking evidence.

## Mathematical design note

- Objects: shared installation value, ordinary compiled graph, root acquisition
  plan, explicit reference-indexed material, private receipt.
- Transformations: installation to graph to deterministic projection; protected
  references to runtime delivery; approved root intent to observed Docker IDs;
  public setup commands to returned durable registration identities.
- Laws: exact projection equality; no secret payload in plan; material validation
  before acquisition; intent before effects; interrupted receipt cannot redispatch.
- Interpreter boundary: root-only ordinary Docker plus authenticated public HTTP.
  Durable workspace/authority/product semantics remain in existing Operations.

## Security and data

New surfaces are the local trusted daemon launcher, private input/receipt files,
and explicit loopback HTTP publication. Public setup uses existing authentication
and exact workspace grants; it never injects actor scopes. Secret files remain
private and are delivered as0400 at image-derived UIDs. SDK/provider exception
bodies are suppressed. No external ingress, DNS or provider resource is created.

PostgreSQL/Secrets volumes are retained durable facts. Docker stages are not
transactional. Public setup retains the existing service transaction boundaries;
the group is not atomic. Any prior receipt stops automatic apply. There is no
automatic rollback, migration, rekey, compensation or replay. An exclusive local
file lock and atomic/fsynced receipt writes protect a single state directory;
foreign resource conflicts are refused. Separate state directories are not a
distributed lock, so creation responses and ownership labels are checked.

Residual risks/provisional behavior: execution remains unvalidated at this
checkpoint; the external HTTPS endpoint is always explicitly unverified; public
registration is not proof that future secret values exist or external credentials
work; completed inspect reports current resource state with historical public
readiness; uncertain helper/effect cleanup requires investigation. Protected file
volumes and retained data are not automatically deleted by production bootstrap.

## Operational reliability and acceptance

The private receipt is root acquisition correlation. CPK's public command results
are the durable initialization truth. Product logs are bounded supplements.
PostgreSQL startup is observed before CPK starts; authenticated public setup and
readback establish local control-plane usability. Failed or interrupted stages
stay HOLD with their last intended action. The example documents plan/apply/
inspect, material shape, driver packaging, optional pull authority and limitations.

Jacob's current direction is one named persistent root for ongoing manual/live
acceptance. The retained root is **not yet created** by this source slice. Its
concrete deployment needs a reviewed plan recording installation/workspace names,
endpoint, immutable images/driver, plan digest, daemon/resource IDs, private
receipt location and public durable-history coordinates. Later acceptance runs
use named workspaces there. Do not create scattered retained installations.

Isolated ephemeral owning/unit fixtures remain valid and use exact ownership and
cleanup. The broader test refactor is deferred. Existing1752/old resources remain
untouched; inventory and any retirement proposal belong to later explicitly
authorized work. Parent/child/grandparent deployment, external reachability and
restart tracking remain separate acceptance boundaries.

## Source review correction (green still stopped)

Meridian's review of b004996 identified four concrete defects: public command
progress was only collected at final helper success; optional ingress did not
bind/read back the returned root provider registration; returned Docker IDs could
be lost if validation failed before receipt persistence; and successful setup
left two one-time staging volumes behind. The fifth reported cleanup-order finding
was withdrawn after re-reading the existing explicit containers/volumes/networks
loop. The owning witness and frozen tests remain unchanged.

The amendment keeps the same root-only boundary. The socket-free helper now
atomically/fsyncs bounded safe progress before commands and after responses, with
returned coordinates saved before later validation. Its exact retained container
provides read-only archive recovery on failure; inspect does not replay it or
rewrite the receipt. The parent copies recovered progress while keeping pending
intent. Success requires complete progress before helper removal. It then removes
only the two exact owned plan/credential staging volumes with intent and absence
evidence; HOLD keeps them intact. Product file and retained data volumes survive.

Optional ingress's generated-secret provider is explicitly bound in the plan to
the actual root provider registration result. Setup substitutes that identity,
preserves the approved remaining authority fields, and checks both command and
public detail against the effective authority. Creation responses now have their
IDs durably saved with pending still set before subsequent verification.

No green execution accompanies this amendment. Independent static re-review is
still required, and no retained-root/provider/DNS/1752 action is authorized here.
