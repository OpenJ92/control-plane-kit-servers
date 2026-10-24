# Managed PostgreSQL artifacts (#191)

Current release rule: package visibility must match the actual owning source
repository (public→public, private→private). This supersedes the earlier
private-only requirement. It changes neither credentials nor package write/admin
permissions, secret handling or CPK authentication. The failed05e84a3 publication
and its authorized deletion remain historical failed evidence.

The native `products/postgres_server/product.cpk.json` remains the historical
official PostgreSQL descriptor. The managed wrapper is a separate selection of
the same product lane: `products/postgres_server/Dockerfile`, Linux/amd64,
configured user `70:70`, cleared upstream entrypoint and the Python wrapper CMD.
The installation driver must use the managed runtime contract; replacing only
the native descriptor's image is not a valid managed installation.

## Publication selection

After separate approval of the exact source and effects, the existing publisher
accepts `postgres-server-managed managed-<full source commit>`. It requires a
clean checkout and the already-existing package
`ghcr.io/openj92/control-plane-kit-servers/postgres-server`. Independent metadata
from `repos/OpenJ92/control-plane-kit-servers` must identify that exact repository
and report public/private visibility consistent with its private flag. The package
must match that repository ID/name and visibility. Access errors, absence,
visibility mismatch and occupied source tags stop before build/push. It never
creates a package or repairs permissions. Build context is the tracked Git archive,
with source revision and Dockerfile SHA256 labels. Platform, user and labels are
checked before the single push; visibility match and unique tag/digest association are
checked afterward. A failed push or verification stops without retry or rollback.
The local built image remains available for inspection.

Publication output is a producer record, not qualification. Registry reads and
tag writes are not atomic; concurrent changes remain a risk. Dependency downloads
inside the recipe mean a source revision alone does not identify output bytes.
Neither this source change nor ordinary CI authorizes dispatching publication.

## Explicit first publication

`postgres-server-managed-first managed-<full source commit>` is a distinct opt-in
selection for creating the real managed image's package on its first push.
The default `postgres-server-managed` selection still requires an existing
matching-visibility package and refuses404. There is no automatic fallback between modes.

Before selecting first publication, the reviewed execution plan must contain
Jacob's explicit attestation that the exact package does not already exist, or
equivalent owner-authoritative absence evidence, and one-attempt authorization
for the exact integrated source/tree/tag/destination. A404 plus a visible-list
miss is absent-or-inaccessible and cannot substitute for that attestation.
Authorization must include package creation matching repository visibility and normal automatic
association/access of `OpenJ92/control-plane-kit-servers`, using that repository's
reviewed workflow and its existing GITHUB_TOKEN (`contents:read`, `packages:write`).
The workflow's existing credential wiring establishes this constraint; environment
strings and the selector do not authenticate a token or grant permission.

The selector repeats the exact package GET before build and immediately before
the sole push. Only HTTP404 with the expected bounded, valid package-not-found
body and failed HTTP command status passes this observation check. Package200,
401/403/5xx, transport failure or malformed response stops. A versions endpoint404
cannot substitute. An observed existing package stops first mode rather than
switching to existing mode. No dummy image or package is created.

The same tracked-archive build adds the explicit owning-repository source label
and verifies it alongside revision, recipe, Linux/amd64 and user70:70. After the
single push it checks the unchanged candidate and these fields again, then requires
the exact matching-visibility package to be associated with `OpenJ92/control-plane-kit-servers`
and its source tag to identify the exact repository digest. Package/version IDs
are not added to stdout. Temporary metadata stays in the private staging directory;
any separately retained copy must remain private unless its disclosure is approved.

Repository metadata is checked before build, immediately before push and after
push; unavailable/malformed/foreign metadata or observed repository ID/visibility drift stops.
The producer line reports matching visibility, never private package/version IDs.
No caller-controlled visibility override is accepted.

GitHub's [workflow-specific creation rule](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions#default-permissions-and-access-settings-for-packages-modified-through-workflows)
inherits the publishing repository's visibility model for a new package created
with GITHUB_TOKEN. The generic private-default statement was insufficient for the
earlier public-repository workflow. Current policy verifies the actual match rather
than assuming either visibility. These defaults do not prove absence. Exclude concurrent writers in the execution
plan, and preserve the non-atomic read/push limitation: there is no transactional
create-if-absent guarantee. If push or post-check fails, a package/image may exist
with unverified state. Stop without another push, deletion, relabel, visibility
change, grant repair or live deployment. Eventual consistency does not authorize
a retry. Actual-digest qualification follows only verified publication under its
own explicit effect scope below.

## Qualifying the actual artifact

After separate authorization, with the exact product digest already pulled and
the established test controller already present, use the owning gate:

```sh
CPK_POSTGRES_ARTIFACT_MODE=published-digest \
CPK_POSTGRES_IMAGE='ghcr.io/openj92/control-plane-kit-servers/postgres-server@sha256:<digest>' \
CPK_POSTGRES_SOURCE_REVISION='<40-character producer commit>' \
CPK_POSTGRES_RECIPE_SHA256='<64-character Dockerfile hash>' \
./test.sh --postgres-published-image \
  --controller-image-id 'sha256:<existing controller ID>' \
  --receipt-dir /absolute/new/private-receipt-directory
```

The witness resolves the exact repository digest once and checks RepoDigests,
source/recipe labels, Linux/amd64, `70:70`, entrypoint and command before creating
fixtures or resources. Every lifecycle container uses the resulting immutable
image ID. Missing/mismatched artifacts fail; no implicit pull, build or alternative
tag exists. The borrowed product image is never deleted.

Published invocations allocate a random run identity inside the new private
receipt directory and retain it as `run.id`. Before fixtures or lifecycle effects,
the witness refuses any existing container, volume or network matching its name
or label. It does not adopt a prior volume returned by Docker's create operation.
Only successfully created objects enter cleanup lists.

The existing witness owns a fresh labelled volume and internal network, temporary
password/control/init fixtures, and its own containers. Its unchanged ladder
checks authenticated management, initial unknown then healthy readiness, retained
row query, graceful stop, same-volume restart, native-child failure, SIGKILL
recovery and wrong-owner refusal. Retained starts preserve #279's native-listener
observation before SQL. No user database or retained installation is accepted as
an input. This does not prove the historical PID-lock cause.

Image admission treats an omitted, null or empty-list `Config.Entrypoint` as
empty, consistent with the publication policy and Docker's
[optional empty inspect fields](https://docs.docker.com/engine/deprecated/#emptynil-fields-in-image-config-from-inspect-api).
Nonempty or malformed entrypoints remain forbidden. The lifecycle admission
regression reaches this check after image reload, before resource creation;
testing only initial artifact selection would miss this boundary. A witness-only
correction does not change the product image: record its runner source separately
from the published producer source when a later qualification is authorized.

Failure summaries can project one numeric refused PID from the existing bounded
native log tail. Missing, malformed, duplicate or truncated evidence retains an
explicit uncertainty state and no PID. No raw hint or path is exposed, and this
message projection does not establish PID ownership, liveness or failure cause.
The original failure and cleanup remain authoritative; diagnostics authorize no
retry, lock removal or data repair.

The JSON success record follows successful lifecycle and resource/fixture-file
cleanup. The shell additionally requires controller completion and removal of the
empty fixture directory; `qualification.exit` must be zero for the whole invocation
to pass. Failures preserve their receipt and do not authorize retry. Abrupt process
death can leave owned resources requiring explicit inspection and cleanup; no
broad prune or autonomous recovery is included. Logs stay private and are not a
public release artifact. The product never receives the Docker socket; only the
test controller has daemon access. The fixed test password is removed afterward.

For source validation only, `./test.sh --postgres-release-tests` with the same
controller/receipt options runs the PostgreSQL unit suite with no network or daemon.
Normal CI retains the existing source-built runtime witness and global residue
audit. Neither path earns published-digest or installed-driver acceptance.

The source lifecycle now uses `--postgres-source-image` through the same owning
shell as published qualification, replacing the former direct controller launch.
Both start the controller on a fresh shell-owned internal bootstrap network so it
can join the witness's internal test network without default-bridge egress.
Controller and bootstrap ownership use a separate namespace from lifecycle
resources; existing freshness/adoption refusal is unchanged. Cleanup removes the
verified owned controller before the exact owned empty bootstrap network.
Unexpected endpoints or uncertain creation/cleanup stop with private receipts;
there is no forced foreign disconnection, automatic retry or SIGKILL cleanup
guarantee. Source mode rejects published selection inputs and retains source image
build/removal. Published mode retains borrowed images. The shell removes only its
exact fixture files after shell resource cleanup succeeds. Source CI proves this
launch composition with source evidence, not artifact qualification.
