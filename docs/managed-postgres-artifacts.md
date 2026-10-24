# Managed PostgreSQL artifacts (#191)

The native `products/postgres_server/product.cpk.json` remains the historical
official PostgreSQL descriptor. The managed wrapper is a separate selection of
the same product lane: `products/postgres_server/Dockerfile`, Linux/amd64,
configured user `70:70`, cleared upstream entrypoint and the Python wrapper CMD.
The installation driver must use the managed runtime contract; replacing only
the native descriptor's image is not a valid managed installation.

## Publication selection

After separate approval of the exact source and effects, the existing publisher
accepts `postgres-server-managed managed-<full source commit>`. It requires a
clean checkout and the already-existing private package
`ghcr.io/openj92/control-plane-kit-servers/postgres-server`. Package access errors,
absent/public packages and occupied source tags stop before build/push. It never
creates a package or repairs permissions. Build context is the tracked Git archive,
with source revision and Dockerfile SHA256 labels. Platform, user and labels are
checked before the single push; privacy and unique tag/digest association are
checked afterward. A failed push or verification stops without retry or rollback.
The local built image remains available for inspection.

Publication output is a producer record, not qualification. Registry reads and
tag writes are not atomic; concurrent changes remain a risk. Dependency downloads
inside the recipe mean a source revision alone does not identify output bytes.
Neither this source change nor ordinary CI authorizes dispatching publication.

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
