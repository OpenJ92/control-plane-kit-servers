# Isolated grandparent product artifact, Servers #163

North released local source/test/build work toward a runnable artifact containing
Vale's tested a544016 startup and Core f56/Ops70154/native e438. No child image
is changed. This preparation is unvalidated; independent source/effect review
precedes Docker work. Registry publication, existing installation cutover, live
sibling bootstrap, customer credential generation, DNS and provider mutation are
excluded. The listening sender startup is a subsequent bounded local proof using
Rowan's exact public variant/configuration input, not a material-driver release.

## Selected package and process path

The dedicated `products/cpk_server/Dockerfile.grandparent` derives from retained
CPK4846, an actual product with default module command and UID10001, through a
verified named local OCI context rather than registry metadata. It removes
inherited server/gateway trees and copies those exact a544016 trees. Local Git
archives supply full package roots for Coref56, Ops70154 and native e438, including
pyproject/build metadata and Operations resources. No test-controller base, host
Python, dependency shim, external runtime source mount or test entrypoint is used.

The same-version0.1.0 distributions are explicitly force-reinstalled from these
local artifacts with `--no-index --no-deps --no-build-isolation`. SDKd61 and native
e438 retain their declared Core976 direct URL; this does not make those declarations
resolver-compatible with selected Coref56. This is an explicitly selected reviewed
cohort. `pip check` is only version consistency, not coordinate proof. No upstream
package metadata is edited to disguise this fact. Existing runtime requirements
are supplied by the accepted product base; missing ones fail the gate.

Build tools only may be acquired from public PyPI: setuptools80.9.0 and wheel0.45.1
with their normal dependencies. PEP517 isolation is disabled for the local package
installs; there is no automatic package dependency resolution or source download.
The exact cached base and controller1c8 must already exist on fixed local daemon
d23d00aa. Buildx uses the existing desktop-linux docker driver, linux/amd64,
`--pull=false`, one fresh tag and run. A bounded local Docker save preserves the
approved OCI index bytes. Its archive and unpacked layout are each capped256MiB,
combined512MiB plus one overflow-detection byte. At least1GiB free space is required
before export. This bounds this action's base transport scratch, not Docker's
whole image/cache store. No builder or resource setting is changed.
No registry credential
or host credential environment is passed. The product image is retained locally.
Public build-only package sources remain in earlier image layers after their
final-filesystem removal; no secret is copied.

`test.sh --grandparent-image-build CORE_REPO OPS_REPO NATIVE_REPO` exports exact
commits and `git ls-tree` blob identities. The image's build-time seal verifies
every package/product source byte against its Git blob, then retains SHA256 file
manifests and source-tree coordinates. After installation the verifier checks
complete source-file sets, all seven Ops SQL resources, distribution RECORD hashes,
direct-URL origins and actual imported package roots against those distributions.
SDK must have its full approved archive URL and import from its verified RECORD
root. No arbitrary module from another site-packages directory can satisfy it.
The normal runtime entry remains exactly
`python -m control_plane_kit_servers_cpk_server.server`, UID10001, port8080.

## Exact proposed source and artifact commands

Run separately from the clean frozen packaging revision, after independent review:

```sh
DOCKER_CONTEXT=desktop-linux \
CPK_SERVERS_TEST_IMAGE=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba \
./test.sh --managed-verification-startup-source-tests \
  /Users/jacobvartuli/.codex/worktrees/dbbb/control-plane-kit \
  /Users/jacobvartuli/.codex/worktrees/dbbb/control-plane-kit \
  /private/tmp/cpk2089-native-postgres-readiness \
  f56bb5c4cfde76764d39c5377d4270c5b23c3ba1 \
  70154b6698e101159326b08646f2dba90dda87cd \
  e438f6e522ad0a23a7acef460be08690f48b2e17
```

Only terminal source PASS permits the following reviewed local artifact phase:

```sh
DOCKER_CONTEXT=desktop-linux ./test.sh --grandparent-image-build \
  /Users/jacobvartuli/.codex/worktrees/dbbb/control-plane-kit \
  /Users/jacobvartuli/.codex/worktrees/dbbb/control-plane-kit \
  /private/tmp/cpk2089-native-postgres-readiness
```

This creates fresh `/private/tmp/cpk163-grandparent-artifact-20261109-02` and tag
`localhost/control-plane-kit-servers/cpk-grandparent:cpk163-sender-20261109-02`.
The existing reviewed gateway ownership helper is reused unchanged for CPK's
bootstrap artifact as a second product consumer. It records the verifier attempt
before Docker, so failure before CID readback still requires exact name/run/owner
and absence checks. Failed inventories stop; build-attempt uncertainty never
becomes a `not-built` claim. A network-none controller validates/extracts the owned
OCI export with1CPU/256MiB/64PIDs, without a socket. The approved index blob, every
blob hash and reachable descriptor size, selected linux/amd64 manifest/config and
normal base process are checked. Named context
`cpk-grandparent-base=oci-layout:///…@sha256:4846…` supplies Dockerfile FROM, with
no tag substitution or registry fallback. This is supported by
[Buildx's local OCI context interface](https://docs.docker.com/reference/cli/docker/buildx/build/#additional-build-contexts---build-context).
The candidate RootFS diff-ID prefix must match the verified base config; candidate
process/platform checks remain separate. Optimized Python refuses before checks.
There is no network or volume allocation in this phase.
The source archives, build metadata, actual RepoDigest/image identity and bounded
installed-cohort report are retained. One named temporary product-image verifier
runs network-none/read-only as10001, no host source mount or socket. Cleanup removes
only that captured owner-matching container if needed and this invocation's build
context and OCI scratch after terminal build, preserving package source archives,
public base proof and candidate. Any submitted build without positive successful
termination confirmation keeps scratch and marks cleanup unverified, including a
failed/disconnected/interrupted buildx child without a signal to this wrapper.
Pre-build failures with no submitted solve can clean owned scratch normally.
An owning fake-CLI regression exercises the actual wrapper's nonzero child path
and verifies retained scratch, failed receipt and no retry. Any ambiguity fails.

The artifact result explicitly says `listening_startup_verified:false`. It proves
packaging/provenance, not a listening sender. Actual default-process listening,
dynamic authority, managed sender public document binding, PG-backed composition,
HTTP readiness/auth refusals, PID1 UID and exact local fixture cleanup require the
next concrete reviewed startup packet. No untested plan is called executable.

The first ecd79e8 artifact invocation is preserved as a terminal pre-package
[BuildKit localhost metadata failure](https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-6748699628),
with no candidate/cohort proof. Read-only diagnosis exported69,618,688 bytes and
verified the original4846 index blob (not merely Docker save's outer index wrapper),
manifest0b1185bd and linux/amd64 config. The revised source adds OCI blob/platform/
wrong-root/optimization regressions to the owning source gate. It needs independent
review and a new explicit build release; the failed reservation01 is untouched.
