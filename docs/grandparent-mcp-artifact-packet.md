# Grandparent MCP artifact and connection packet (#401 / #399)

Accepted packaging/build source is2cf6cba37b2e951c4c51b2bb211c4bf10a7dd033;
its source gate, dependency inventory and local image build passed independently.
The first isolated normal-process attempt stopped before helper startup at a
mount-layout defect, with owned cleanup verified and no runtime credit. A narrow
driver correction preserves that image and its original build receipt. Wrapper
source evidence never substitutes for actual normal-process qualification.
This packet does not release a build, pull, publication, credential read,
current-installation inspection, replacement or client configuration change.

## Accepted source and selected inputs

PR402 merge `0610e9454dd9a75a6e6bf5e89fe281c8631cccaa`, tree
`f5ade2a5310a993f6bf34c207580603531312bf4`, is the product source. Its reviewed
head1fad0c9 passed focused202/209, full1380 and CI43482682327. The packaging
checkpoint is a separate clean commit on `codex/399-grandparent-mcp-packet`
from that merge; proposed destination remains `roadmap/1813-runtime-control`.
Record its exact hash in the issue before any execution.

The runtime retains Coref56bb5c4, Ops70154b66, Interpreterse438f6e5 and SDKd61b374.
Interpreters uses the explicitly admitted retained Git export SHA256
`af15d9261cde91e387b2659b489712abbc5579f09ba67ca51350c802552c22e0`, PAX commit
e438f6e5 and module tree97507ed0. Missing Git objects never select a fallback.
All four complete package archives and both product trees are source-sealed.
SDK source/RECORD/import identity is now checked, rather than only its archive
URL. SDK and Interpreters still declare Core976; no metadata or root pin is
rewritten to conceal the deliberately selected cohort.

The product base remains cached
`localhost/control-plane-kit-servers/cpk-server@sha256:4846a9005108e925149b2869214c3f32dbdbd4d4953159af532297081e80fe28`.
The historical source/helper owner is23bcab; the consumed artifact02 command,
tag and record are not reused. No current cache availability is asserted.

## Public dependency lock and true baseline gap

`mcp-grandparent-public-lock.json` selects28 runtime wheels, including MCP2.3.0,
for Linux amd64 / CPython3.12. Versions and wheel filenames were observed in the
accepted focused run; SHA256 values come separately from each versioned PyPI
metadata URL. This is not an attestation of the earlier downloaded wheel hash.
The root MCP requirement source is the official SDK's frozen2118f14f pyproject.
CLI/rich and other optional extras are excluded; PyJWT's required crypto path
is included. Unrelated Docker/PG/requests/Jinja product dependencies are not
silently replaced by the MCP lock. Build tools retain setuptools80.9.0/wheel0.45.1
with separately pinned public wheel hashes.

The historical artifact receipt does not inventory all public dependencies.
The actual cached-base presence/version delta is UNKNOWN. The proposed policy
allows only additions and explicit same-version wheel reseals; it refuses a
different existing version before package installation. A version difference
requires a reviewed lock/delta decision, not an automatic upgrade or resolver
fallback. The SDK's recorded FastAPI0.141.1 remains an explicit prerequisite.
No Secrets distribution may be present.

## Existing owner entrances and proposed identities

These are extensions of the historical grandparent owner. Only the source-only
gate has run; all artifact actions require independent review and the stated release.

1. Source-only owning Docker gate:

   ```sh
   ./test.sh --grandparent-artifact-source-tests
   ```

   It uses the retained full-gate controller
   `sha256:4eb536f196cb67260426f8902fca63959d414673c43bcd6e0008ff4712fd8c22`,
   no pull/build/socket/network, the existing policy/support/integrity owners,
   historical OCI tests, actual-wrapper nonzero-build stop test, and bounded
   dependency-inventory laws. Docker/Git facts in the build-stop law are finite
   doubles; these cannot qualify an artifact. Missing controller stops.

2. Separately released read-only artifact dependency preflight:

   ```sh
   DOCKER_CONTEXT=desktop-linux ./test.sh --grandparent-image-plan
   ```

   Proposed run `cpk399-grandparent-dependency-plan-20261113-01` is not reserved.
   It admits daemon d23d00aa-b281-448d-bc95-c8e47efeeea2 and exact cached base,
   then runs one named UID10001, network-none, read-only metadata process with
   1CPU/256MiB/64PIDs and16MiB tmpfs. Only the verifier and public lock are bound
   read-only. There is no socket, credential/configuration mount, server import,
   service startup, provider call or image pull. It reports the28 public
   versions and exact proposed delta, with `server_started:false` and
   `credential_or_configuration_read:false`. A successful observation may still
   say `review-required`; that is not build admission. Owned actor absence and
   base retention must be verified. No current installation is inspected.

3. A later, separate build release, only after source gate and reviewed
   ready/no-version-change preflight at the same packaging commit:

   ```sh
   DOCKER_CONTEXT=desktop-linux ./test.sh --grandparent-image-build \
     "$CPK_CORE_SOURCE" "$CPK_OPERATIONS_SOURCE" \
     "$CPK_RETAINED_INTERPRETERS_EXPORT" "$CPK_SDK_SOURCE"
   ```

   The four locations must resolve to the already reviewed exact source inputs;
   record their actual coordinates privately before release. Proposed run
   `cpk399-grandparent-artifact-20261113-01`, tag
   `localhost/control-plane-kit-servers/cpk-grandparent:cpk399-mcp-20261113-01`,
   and immutable cached OCI controller1c8b3fc3 are not reserved or reobserved.
   A pre-existing name/tag/record or failed inventory stops. Reuse the bounded
  256MiB export/256MiB layout,1GiB free-space prerequisite, named local OCI base,
   linux/amd64 `--pull=false`, one build attempt and historical ownership helper.
   Public wheels use direct hashed URLs, no index/dependency resolution;
   project archives use no deps/build isolation. Keep UID10001, empty entrypoint,
   normal server command and explicit `grandparent-read-only-v1` image default.
   The verifier checks source/RECORD/origin/import identity, actual MCP and the
   public lock. A non-successful/ambiguous submitted build retains scratch and
   marks cleanup/retention unverified; never retry automatically.

   Packaging success still records `listening_startup_verified:false` and
   `approved_deployment:false`. No registry publication, network/volume/service
   allocation, host-source runtime mount or existing-state adoption is included.

## Named isolated built-image qualification proposal

The existing owner `scripts/cpk_server_image_smoke.sh` now contains a closed
`grandparent-artifact` profile, entered only by this separately released command:

```sh
DOCKER_CONTEXT=desktop-linux ./test.sh --grandparent-artifact-qualification \
  "$CANDIDATE_IMAGE_ID" "$PUBLIC_BUILD_RECEIPT" "$CACHED_POSTGRES_IMAGE_ID" \
  cpk399-mcp-qualification-20261113-02
```

The corrected driver is unqualified. Both image IDs must be full cached sha256
IDs; the successful public build receipt must match accepted packaging2cf6cba,
accepted product0610, exact candidate digest/cache identity and verified retained
base/cleanup/cohort. A missing image or receipt stops without pull/build. Exact
PostgreSQL image ID and source must be reviewed before execution. The proposed
run02 is not reserved; consumed failed01 must not be reused. This profile does not use wrapped-artifact's different
CPK/Secrets admission tuple and does not change the ordinary smoke profiles.

The proposed fixture is a new labeled private network and disposable PostgreSQL
database, no published port or provider/daemon socket in the product. A candidate-
image helper generates throwaway setup and read-only credentials plus public
receiver/authority/managed-health/managed-verification JSON into owned private
fixture storage. No protected existing file or credential is copied. Product
startup uses its normal command as PID1/UID10001, with real bounded file readers,
real PostgreSQL services and actual auth; no predecoded configuration or replaced
factory/listener. Bootstrap authority/receipt uses existing Operations/initializer
owners. After bootstrap, fixture graph/revision setup uses authenticated HTTP.

Fixture construction reuses current receiver/native product fixtures and the
qualified public sample/gateway/PG descriptor owners. It must encode actual
managed configuration, not port full child authoring merely to construct data.
Record canonical public input hashes and versions; keep generated values private.
The reader credential has only workspace read; a distinct setup actor owns the
explicit fixture setup/HTTP planning request. No authority is inferred from MCP.

The source reuses `gateway_packaged_owner.sh` for daemon/name/label/cid capture,
owned volume/network cleanup and residue verification. New helpers use the
candidate image with a different entrypoint and read-only witness source only;
the five existing public witness files are staged in one new owned directory
and mounted once, avoiding missing nested targets beneath a read-only bind.
the normal product has only its four generated public files, no source overlay,
provider socket or published port. Client helpers share the candidate network
namespace and call loopback HTTP. Generated credentials/env/saved fixtures stay
in a newly reserved0700 directory and are never printed. Success removes that
private and public witness directories after exact resource cleanup; uncertainty
preserves both. The receipt records actual clean driver source separately from
the frozen accepted built source; installed cohort must match the latter.

Required observed proof: real file decode and listening/readiness, installed
cohort/public lock and PID1 identity; exactly four MCP reads and HTTP parity for
the seeded saved revision/history; missing/wrong auth and direct command refusal
even with setup authority; both protocol eras; normal unchanged-state restart;
actual HTTP managed-intent/fences/key forwarding and preserved saved state.
The fixture deliberately saves an empty graph, so real managed SQL/HTTP planning
must return `review-blocked`; its public plan must show the managed profile and
exact observed fences. One explicit replay of a known successful HTTP response
checks the same caller key keeps the same plan/history. This is no claim of a
deployable managed graph or ambiguous-effect recovery. Both pre/post restart
checks preserve the actual saved revision, preparation and empty attempt history.
The separate accepted recording-port test remains a composition double, not this
real-planner witness.
No approval, provider effect, material write or child deployment is needed.
Capture all owner IDs before effects; prove exact fixture cleanup and preserve
uncertainty on failed reads. This isolated state never substitutes for #163.

## Existing-state connection preflights and blockers

North's historical coordinates are lookup anchors only: installation
`cpk163-gparent-20261109`, API18163, website18164; workspace
`cpk163-child-20261109`; draft000f2e90-ece8-4584-8425-89fecb0b98a5 revision1;
Desired773b4491-06ac-494f-abf5-5f1c199c66bc generation1;
Current17c48b45-feb4-43ca-85e6-3e0a662a00aa; blocked
plan59b13f1d-a67c-4ed6-b08c-93a661f317c6. They are not current attestation or
rollback targets. The historical artifact62e4ee7f is not current-container proof.

Before a replacement/connection approval, obtain these bounded read-only facts:

| Blocker | Smallest observation / owner | Stop boundary |
| --- | --- | --- |
| Public base delta | Reviewed `--grandparent-image-plan` above | Version mismatch or missing cache stops; no pull/upgrade |
| Current instance/resource identity | North/installer owner projects exact current image, container, database/store mapping, protected mount references, installation/journal ownership and effective public MCP profile without values or protected file contents | Exact inspection command/projection must be reviewed first; no replacement/reinitialize |
| Existing saved state and attempts | Authorized existing HTTP reads: workspace, Desired, exact historical revision and its attempt/history coordinates; record fresh fences and outstanding/ambiguous work | Missing/crossed state stops; no newest-record guess or replay |
| Read-only identity | North/security owner supplies issuer/subject/kind, workspace-read scope, credential logical reference and custody owner, never value | Existing setup read/edit/planning identity is not relabeled read-only; new grant/credential needs separate approval |
| Installed client delivery | Select actual Codex GUI/CLI target/config root, binding delivery/removal and reload/restore using a bounded selected-entry projection | No raw config dump, environment values, GUI-shell inheritance assumption or change before approval |

Only after those observations can a review name exact old/new image, quiescence,
preserved database/schema/graphs/history/authority/mounts/journal, replacement
command, verification and safe rollback. Do not regenerate material, replay an
ambiguous attempt, initialize a new database, grant authority, or replace the
existing installation to obtain a clean fixture.
The eventual runtime packet must explicitly set and observe the four-read profile;
an inherited container environment can override an image default. Project only
that public flag, rather than dumping protected environment/configuration data.

The eventual minimal client stanza uses the chosen endpoint plus privately
delivered bearer reference, exactly `get_workspace`, `get_desired_graph`,
`get_desired_topology_draft_revision`, and
`list_desired_topology_draft_revision_attempts`. `CPK_MCP_BEARER` is only a
proposed logical name, not an established destination. Preserve unrelated client
settings. Validate actual installed Codex discovery and reads of the reobserved
existing state after its demonstrated reload; SDK/CLI source tests alone do not
prove GUI adoption. Removal must restore the selected entry/binding and report
that server credential revocation is a separate owner action.

## Next permitted decision

Meridian reviews this exact unexecuted source/plan checkpoint. The smallest next
release is the owning source-only gate; after PASS, separately release the
read-only cached-artifact inventory. Review its actual delta and complete the
named isolated profile/fixture source before any build/qualification request.
Current-runtime/identity/client preflights remain separate, bounded, explicitly
released reads. Build, publication, existing-state replacement, credentials and
client edits are not approvable from unknown coordinates. #163/Vale material
work and the #403–#415 planning topology are not advanced by this packet.
