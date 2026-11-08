# Child packaged-image preparation for #163

Status: proposal only, 2026-11-08. No build, acquisition, publication, allowlist
edit, catalogue update or deployment is released by this document. North owns
scope/release; Linnaeus owns image receipt/qualification evidence; Rowan owns
the consumer source/input. Account usage at preparation:62%, cap64%.

Correction to ad80738: the claim that Ops976 lacked health_receiver_trust and
therefore forced a CPK dependency upgrade was wrong and is withdrawn. The
authoritative pinned source contains HealthReceiverDecoders at line202, blob
30fecc638839feef680b2953e9aac2eca1e83b18. The local Git error was insufficient
evidence of absence. No build, dependency upgrade or acquisition was performed
from that premise. Kepler owns the actual unchanged child-serving-path trace.

## Existing evidence to carry forward

- PostgreSQL: retain #390 and
  `localhost/control-plane-kit-servers/postgres-server@sha256:8ddc847725e9b1d4c931dce2590c59d5bf68104c5804441ed2ed80e99778b48b`.
  Do not pull, retag or remove this borrowed image.
- Connector: reuse accepted [#356](https://github.com/OpenJ92/control-plane-kit-servers/issues/356#issuecomment-6516024892)
  for candidate812262a6 from producercc1b8d87. One image serves three nodes.
  Lin supplies its full exact reference/platform association and child control,
  token-delivery and route settings. A different SDK pin alone does not demand
  repeating that historical qualification. Do not edit the historical version
  allowlist to include local Docker29.7.2 or claim its stop behavior was covered.
- Website: reuse [#190](https://github.com/OpenJ92/control-plane-kit-servers/issues/190#issuecomment-6672344849)
  packaged image ID
  `sha256:b680e712ea12ab67f5151817621a82b29b947a1747da3f1c3adab3b9eb52b095`.
  Verify full local OCI-reference association and architecture separately.
  Index/JS, authenticated local readiness and negative/stop evidence are reusable;
  the actual child upstream, public ingress and customer login remain separate.

The [six-role evidence update](https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-6725082120)
and [three-role plan](https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-6725124971)
govern this continuation. Prefixes are inventory labels, not runnable references.

## Child requirements versus grandparent execution

Use tested Servers85b193bbdc777376c5104029a5ee04e74627cf71 source for the three
remaining products. Later Servers commits change receipt documentation only.
The grandparent qualified Coref56/Ops701/Ie438 via exact source archives; that
does not require every child product to install that whole tuple.

| Child | Actual path | Dependency conclusion before any build |
| --- | --- | --- |
| CPK | server entrypoint → operations_application factory; Core/SDK HTTP sample receiver, four SQL-backed stores; configured Interpreters runtime adapter | Ops976 DOES contain health_receiver_trust and HealthReceiverDecoders. No mandatory upgrade is established by that import. Trace and qualify Source85 with the unchanged recipe first; advance only an identified required interface. Ops71 is not a drop-in alternative with Core976: it imports a compiler absent from that Core. The child does not automatically need the grandparent's SQL execution profile. |
| Secrets | product server launcher → Secrets.application.app_from_environment + SDK sample loader/receiver | Child serving needs the existing HTTP sample binding, provider startup and custody/restart interfaces. Secrets57 differs from158 only in provider_policy's two signing intents; that is parent commissioning support, not an intrinsic child HTTP requirement. Preserve158 implementation unless a concrete child interface fails. |
| Gateway | product server → V2 health relay and HTTP sample relay/configuration | Requires the existing Core request/grant/configuration/result codecs and SDK management wrapper. No Operations, Interpreters or Secrets package is needed in this image. |

Static evidence: Core976→054 changes only Core root/planning and secrets.py;
HTTP sample request/installation and V2 receiver read/route modules have no delta.
SDKd61's wrapper loader is the selected receiver interface. Secrets57→158 has
no application/control/API delta. This is source interface evidence, not an
executed old-dependency image qualification. Child Secrets/gateway may retain
their current implementation dependencies if their owning packaged checks pass.

## Existing tuple, and conditional upgrade closure

Current maintained recipes/canonical coordinates select Core/Ops
`976901c609d950a557ec1e9966f018e8ff6e16aa`, Interpreters
`e4bd35e828d1c44129f64e702de2b1d2b60f7c87`, SDK
`d61b374cb2a23d773c31748f47f88169499298b7`, Secrets
`158b17ed10689360c4e1529a395b3ee2b47aecbc`.

The final execution candidates are Core
`f56bb5c4cfde76764d39c5377d4270c5b23c3ba1`, Ops
`70154b6698e101159326b08646f2dba90dda87cd`, native implementation
`e438f6e522ad0a23a7acef460be08690f48b2e17`.
Core package trees at f56 and701 are identical9b69911e9b15207d1900e0967612d8a6ffa14fc6.
This remains the grandparent execution tuple, not automatic child pin adoption.

The existing declared child tuple is not shown to have a dependency conflict.
It is the first candidate to verify. The source-built grandparent tuple above
is a separate, qualified execution context; do not substitute it speculatively.

Conditional metadata conflict if advancing CPK to that newer tuple: SDKd61 and Ie438 each
Require-Dist the exact Core976 URL; Secrets158 does too. Ops701 merely requires
Core>=0.1.0. A recipe asking for Coref56 together with those unchanged direct
references declares different sources for the same distribution. Normal
dependency resolution must be satisfied; sequential pip replacement, --no-deps,
PYTHONPATH substitution or ignored pip-check failures are not packaged evidence.
No resolver experiment/red result is claimed here.

Authoritative checks for the correction:
[Ops976 HealthReceiverDecoders](https://github.com/OpenJ92/control-plane-kit/blob/976901c609d950a557ec1e9966f018e8ff6e16aa/control-plane-kit-operations/src/control_plane_kit_operations/health_receiver_trust.py#L202),
[Ops71 compiler import](https://github.com/OpenJ92/control-plane-kit/blob/71db67c5df666d936860cce35b99394e600b2f1f/control-plane-kit-operations/src/control_plane_kit_operations/plan_derivation.py#L15),
and [Core976 planning exports](https://github.com/OpenJ92/control-plane-kit/blob/976901c609d950a557ec1e9966f018e8ff6e16aa/control-plane-kit-core/src/control_plane_kit_core/planning/__init__.py).
The latter has no compile_http_sample_bootstrap_activity_plan export. An
Ops71/Core976 mixture must not replace the internally consistent existing tuple.

Availability: read-only GitHub commit probes returned422/no-commit for Ie438
and Secrets57. They are qualified local source coordinates, not currently
installable public archive URLs. Do not generate such URLs until source owners
make the reviewed commits or equivalent reviewed successors available.

### Smallest viable choices

| Choice | Required work | Disposition |
| --- | --- | --- |
| Existing recipes, unchanged dependencies first | Use Source85 with the existing declared tuple after Kepler's path trace and owning packaged checks. Only a concrete missing interface justifies a dependency change. If one is found, use normal reviewed source branches and the existing coordinates/server-products.json → apply_coordinates.py owner; reconcile the conditional direct-Core requirements and inspect every generated change. | Preferred: no pin change is presently justified. Existing recipe/dependency/provenance owners are preserved. No global/live adoption or invented successor SHA. |
| Verified local package artifacts | Build verified wheels/sdists from exact source, record source/content hashes and satisfy the same Requires-Dist closure. Current Dockerfiles accept explicit remote URLs, not a local wheelhouse; a small reviewed opt-in install path and corresponding local-artifact provenance checks would be needed. It does not solve contradictory Core metadata. | Fallback only if normal source publication is unavailable and this extra path is specifically released. Do not build a packaging framework or bypass metadata to make it work. |

Prefer independent child versions when interfaces permit. The current coordinate
manifest has one shared upstream tuple and its generator updates multiple
recipes. If that owner requires a common Core/SDK cohort, document that constraint
and use metadata-only alignment where possible; do not silently promote unrelated
runtime implementations. A lower CPK implementation cohort must be proved by its
own import/entrypoint/package checks rather than inferred from the parent tuple.
No metadata successor/source publication is a prerequisite if the unchanged
child-serving dependencies satisfy the actual selected interfaces.

## One released build per missing role, owning qualification

Prepare a narrow named selector in existing test.sh, reusing existing owning
steps. It is missing today: the source-composition selector only uses a
socket-free controller, while the ordinary full gate would repeat unrelated
products. The new selector should build each of the three role recipes exactly
once for linux/amd64, retain those images, then test those exact image IDs.
This selector/source change and source metadata need normal review first.

| Role / existing owner | Required real packaged observations and bounded additions |
| --- | --- |
| CPK: products/cpk_server/Dockerfile, scripts/cpk_server_image_smoke.sh, source_control_fixture.py, scripts/http_sample_fixture.py | Default entrypoint and actual numeric process; missing configuration/unsigned/wrong authority refusal; all four named database URLs wired and usable, with inconsistent binding refused; original live AND ready served and signed-sampled with matching target/check/digest. Existing smoke exercises both ordinary endpoints but the signed sample helper selects only ready. Extend that maintained helper to both original checks; do not replace the contract. |
| Secrets: products/secrets_server/Dockerfile, scripts/secrets_server_image_smoke.sh, source_control_fixture.py | Real provider initialization/authentication, encrypted custody and restart using owned storage; both original live/ready checks and wrong-authority refusal. Existing signed helper is ready-only and needs full original pair coverage. Its wrapped-source mode currently owns its build; factor its maintained steps so the narrow selector tests the one retained image without a second build. |
| Gateway: products/cpk_local_gateway/Dockerfile, products/cpk_local_gateway/tests/live_wrapper_artifacts.py and existing relay fixtures | Real default packaged process, signed V2 relay plus HTTP samples forwarded to selected packaged CPK/Secrets; exact request/receiver/check and installed trust/route bytes; wrong trust/target/expired window refuse. Reuse the image-owned V2 witness rather than treating unit relay tests as image proof. Select the narrow gateway witness without rebuilding unrelated Hello or rerunning historical connector/website qualification. |

Per-image receipt: full producer source and recipe hash; requested and actual
installed dependency source/Requires-Dist/direct_url metadata; successful normal
dependency check; image/config ID AND full immutable OCI reference association;
OS/architecture, numeric process identity, actual entrypoint and behavior results;
fixture IDs/ownership, terminal result and cleanup. A build label/controller
import or image ID alone is not a runnable OCI digest or installed-source proof.
Any local platform/emulation delta from reused evidence is named separately.

The release packet must name exact source/dependency commits, three fresh unique
local destinations, acquisition policy/bounds, owning selector, isolated network,
owned database/storage/control material, retained images and exact cleanup.
Reuse verified cached bases where possible. Needed acquisition is declared before
execution; no implicit pull of a selected historical image or automatic retry.
Stop on source drift, metadata conflict, unsupported engine/platform, failed
behavior, unknown resource ownership or cleanup uncertainty. No broad prune.
Private signing material and credentials stay fixture-owned/redacted; only
bounded public receipts survive. Existing published/historical allowlists stay.

## Authorization and next consumer boundary

This preparation performs only source/GitHub reads and documentation. Source
branch publication/metadata adoption, the exact local build/qualification action,
and any acquisition need their existing owner release before execution. No new
general permission or production credentials are requested. Registry publication,
release workflows, installed-grandparent changes and live deployment are outside
this plan. No action was attempted and rejected by automatic approval review.

After Lin supplies six full qualified references/receipts, parameterize all six
image roles before one commissioning/graph assembly. Use actual graph-imported
installation variant descriptors for PG observer and management connector;
repeated identical connector documents represent one imported product value.
Hold keys and immutable versions for that same workspace/session. Recompile that
exact selected graph: original SQL wait, CPK/Secrets live+ready, four DB bindings,
three connector starts and ingresses remain. Only normal approved public
prepare/approve/execute and committed SQL/HTTP history can establish the child
installation. Source/image qualification does not invent or seed those outcomes.
