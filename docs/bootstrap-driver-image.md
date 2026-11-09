# Complete offline installer driver — Servers #384 / #163

This driver is separate from accepted grandparent runtime62e4 and accepted child
images. It never serves CPK. Its default is the normal installed
`python -m control_plane_kit_servers_cpk_server.bootstrap_cli`, USER0/no entrypoint;
ordinary bootstrap.sh plan/apply/material commands choose the caller UID and
explicit CLI as before. Apply/prepare remain later consequential actions.

## Source selection and package shape

The isolated branch `codex/384-bootstrap-driver` combines reviewed Vale material
bfed7ab7737f067039c1015f9e7b47392889a0d8 (default+optional policy) and parent website
b69417850efa1f4aecf4f567621abf79c21cda8b with the qualified runtime build tools.
Source selection checks ancestry AND exact loader/material/website production
files against their owner heads before Docker work. The full Servers package is
exported from the actual clean reviewed build HEAD, which is stamped into the
derived cohort manifest; tracked `servers:null` is not a fake selected commit.

The dedicated Dockerfile derives from cached controller1c8, explicitly as an
installer base. Its measured compressed size is102,133,175 bytes. It installs
Coref56/Ops70154/native e438/Secrets57 and the whole selected Servers wheel from
Git/blob-bound local exports, same-version force-reinstall, no index/deps/build
isolation. Only setuptools80.9.0/wheel0.45.1 and normal tool dependencies may fetch
public PyPI. SDKd61 remains inherited and verified. Source overlays are cleared;
the normal production CLI resolves installed modules, not controller /app code.
Actual installed Requires-Dist URLs are checked and reported separately: the
Servers declaration still selects Secrets158/Core+Ops976/native e4bd, and SDK,
native and Secrets still declare Core976. These declarations are not silently
fixed; selected runtime source/RECORD/import provenance supplies the cohort proof.

All installed package source sets, distribution RECORDs/import roots, full SDK
archive URL and seven Operations SQL resources are checked. Required imports
include real bootstrap_cli/bootstrap/material, Secrets.control/bootstrap,
website.managed, PostgreSQL.configuration and Docker/HTTP/DB/crypto dependencies.
The normal root plan needs these; the runtime CPK image is not this driver.

The existing local OCI mechanism exports the exact controller root digest,
validates all blobs/descriptor sizes/platform/config with its DISTINCT root/test
base process policy, then gives BuildKit a named local OCI context. Its old test
CMD is not retained as the driver CMD. There is no registry resolution/fallback,
new builder, tag-as-proof or Docker daemon change. Candidate RootFS must retain
the verified base prefix. The archive/layout are each capped256MiB (combined
512MiB plus one overflow byte), with1GiB minimum actual free disk. The bound is
owned transfer scratch, not the whole Docker image/cache store.

## Exact proposed tests then one build

Run separately from the frozen reviewed source; no driver effect has run yet:

```sh
DOCKER_CONTEXT=desktop-linux \
CPK_SERVERS_TEST_IMAGE=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba \
./test.sh --bootstrap-driver-source-tests \
  /Users/jacobvartuli/.codex/worktrees/dbbb/control-plane-kit \
  /Users/jacobvartuli/.codex/worktrees/dbbb/control-plane-kit \
  /private/tmp/cpk2089-native-postgres-readiness \
  f56bb5c4cfde76764d39c5377d4270c5b23c3ba1 \
  70154b6698e101159326b08646f2dba90dda87cd \
  e438f6e522ad0a23a7acef460be08690f48b2e17 \
  /private/tmp/cpk163-secrets-http-source \
  57e4fc61d6931ef078550f98154a585bda61987b \
  /private/tmp/rowan-384-root-bootstrap-input.template-v2.json
```

The owning suite retains policy/support/integrity, exact four source exports,
material/default+optional policy, parent website, sender startup and packaging
regressions. New additive imports/normal CLI composition checks run before build.
Only terminal PASS plus independent exact-source/effect review permits:

```sh
DOCKER_CONTEXT=desktop-linux ./test.sh --bootstrap-driver-image-build \
  /Users/jacobvartuli/.codex/worktrees/dbbb/control-plane-kit \
  /Users/jacobvartuli/.codex/worktrees/dbbb/control-plane-kit \
  /private/tmp/cpk2089-native-postgres-readiness \
  /private/tmp/cpk163-secrets-http-source \
  /private/tmp/rowan-384-root-bootstrap-input.template-v2.json
```

One fresh tag `localhost/control-plane-kit-servers/cpk-bootstrap-driver:cpk384-20261109-01`,
records `/private/tmp/cpk384-bootstrap-driver-artifact-20261109-01`, fixed local
daemon d23d, cached controller1c8. No network/volume/service allocation or socket.
Only named owned base validator, installed-provenance process and normal CLI
qualification containers run, network-none/read-only, bounded tmpfs/resources.
The last runs as the actual host UID/GID, as normal offline bootstrap planning does.
Cleanup follows the existing attempted-role/cid/name/run/nonce/daemon discipline;
unconfirmed submitted build retains scratch and fails cleanup. Candidate/base
are retained/rechecked. Stop at first failure/uncertainty; no automatic retry.

## Finished-image CLI evidence, not a customer plan

The helper uses the maintained synthetic public-only fixture (keys in memory,
no private PEM files) inside the finished image. It calls actual installed
material plan and bootstrap plan subprocesses with the ACTUAL driver image ID,
checks matching owner-computed digests, managed website artifact preservation,
both explicit HTTP import intents and default/optional fixed-policy planning.
An HTTP generation policy request must refuse exactly exit2/empty stdout/fixed
bounded reason; crash/killed process is not counted as policy refusal. Optional
planning names an extra credential output but creates none. No material prepare,
apply, real customer manifest, grant, listener, ingress or deployment is executed.
Public summaries contain digests and booleans, never values or raw private output.

Qualification also takes a bounded read-only snapshot of the frozen public
root template-v2 (SHA256f81ba76a…24b7). It projects its EXACT health and sender
artifacts into the synthetic fixture, checking mounted content/paths and
`docker-unix-v2` plus dynamic authority through the actual normal installer.
Its website remains synthetic; this does not re-render or replace the customer's
frozen website identity. The actual customer template is not executed or mutated.
The public snapshot is an input to qualification, not baked customer data or a
source overlay in the generic driver. A changed snapshot refuses before build.
Both material modes use the health artifact's exact capability set. Product
descriptor mappings enter the codec as mappings, preserving its canonical-byte
entrance contract. These fixture corrections were independently identified
before either source qualification or image execution.

Real preparation must separately bind the accepted driver ID, qualified parent
Secrets selection, frozen public sender/gateway/PG/website/health/connector files
and reviewed customer policy. The child six-image tuple remains unchanged.

## Completed offline qualification

Reviewed/tested build source is b46d4715964fcd4a0b89130e2774cece2481b0ed.
The separately released source gate passed28 support and49 focused tests
(75.405s), with policy/integrity and owned cleanup. The single local artifact
action completed exit0, retained both base and candidate, and verified cleanup.
The immutable installer is
`localhost/control-plane-kit-servers/cpk-bootstrap-driver@sha256:8134f1032d1fb78947f367c9e848506021b8da4d76c66d465fb7057112aa962d`.
Both installed normal CLI modes passed the public/synthetic projection checks.
The [durable receipt](https://github.com/OpenJ92/control-plane-kit-servers/issues/384#issuecomment-6750722926)
records the source, installed provenance and bounded plan/cleanup evidence.
Independent terminal artifact review and North's disposition are separate from
this executor receipt. Real material preparation and startup remain unexecuted.
Any later documentation-only commit is not the image's built Servers source.
