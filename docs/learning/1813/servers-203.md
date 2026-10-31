# Servers #203: Secrets source product adoption

Parent [#189](https://github.com/OpenJ92/control-plane-kit-servers/issues/189)
records the final two-child decision in
[comment5651900885](https://github.com/OpenJ92/control-plane-kit-servers/issues/189#issuecomment-5651900885).
This child starts from accepted roadmap base18b5f0e795a15f471f187956041211d1403cfc27
and targets roadmap/1813-runtime-control. Secrets service acceptance is
0e0fa2c8fc1464f8ea3ac4ad9a515a9b438820be. Child204 will restore the maintained
standalone source smoke; parent189 remains open until both pass.

## Law context and source dry run

Secrets owns its typed public configuration, closed encoder/decoder and actual
SDK/private-startup behavior. Servers owns wrapping those bytes as
secrets-control JSON0444 at /etc/cpk/secrets-server/control.json and the complete
source runtime contract. The proposed public functions are
secrets_control_configuration_artifact(configuration) and
secrets_source_runtime_contract(artifact), in the product's configuration module.
Malformed product framing has a fixed SecretsProductConfigurationError.

Existing product descriptor, socket/port, bootstrap/private-file, recipe and
image-smoke tests govern this child. Preserve HTTP control8081, numericUID10006,
retained provider-data and lifecycle, two private0400 nonrecursive inputs,
HEALTH_CHECKABLE and both existing live/ready verification checks with complete
policies. Add the separate public artifact and actual Secrets
V2 liveness declaration/NODE_CONTROLLABLE. Historical published descriptors,
catalogue and image/source provenance remain unchanged until actual qualification.

Source adoption selects the actual accepted Secrets codec through an installed
pinned dependency and product package; it does not copy service semantics.
Canonical coordinate generation owns dependency mirrors. The fresh numeric
source witness must receive real public configuration through existing artifact
materialization while retaining its full private/UID/data/auth/cleanup laws.
Historical published/root stages keep their existing image contracts. During
this intermediate child, standalone source mode must fail clearly before any
Docker operation or cleanup trap;204 restores it before parent closure.

## Focused target-test checkpoint

Six new tests classify as product new-law or strengthened composition laws:
canonical service bytes/product framing; complete prior contract preservation;
invalid artifact framing/service input; invalid or forged typed configuration;
recipe/public-bootstrap/private/published agreement; and installed public import
plus dependency identity. The existing product contracts are isomorphic inputs,
not permission to recopy upstream custody or SDK state machines. Test fixtures
use actual Core/SDK types and import the accepted service only after an explicit
product-interface guard; no test stub supplies a missing implementation.

North specifically chooses one intended-red checkpoint for this new interface
under the owning calibrated loop. Tests precede application implementation.
At the original target checkpoint the tests were unexecuted; explicit
missing-interface guards were expected to fail with downstream laws unreached. Only the existing full owning
Docker-backed runner may establish red after exact effect review/release; no
custom selector or import/collection fault can substitute. Later source and
fixture review, full green and matching hosted validation are required.

Security/data: preparation creates no credentials, provider resources, runtime
mutation or public exposure. The target tests construct public values and later
inspect a cold import; real fixture authority/effects need separate review.
Product artifact production here is a pure value transformation, not authorized
production materialization or immutable OCI qualification. Those boundaries and
held runtime acceptance remain in their existing issues.

Source-aware target review found that Core's PublicStaticEnvironmentBinding
rejects names containing secret, so the accepted service path variable cannot
be a graph public binding. The corrected contract preserves public_environment
exactly. Docker ENV fixes CPK_SECRETS_CONTROL_CONFIGURATION_FILE to the canonical
public artifact path; bootstrap documentation and the numeric recipient witness
protect that recipe/process ABI. No Core safety rule, service variable name or
private delivery semantics changes. The full-contract target keeps this field
inside its unmodified-field equality, and artifact framing also rejects valid
changed content with stale digest metadata. No red run occurred before this
review correction; prior target disposition is superseded pending reseal review.

## Classified red and current source checkpoint

The [bounded red result](https://github.com/OpenJ92/control-plane-kit-servers/issues/203#issuecomment-5652021440)
records26 policy tests and all389 predecessor package methods green. All395
package methods collected, with exactly six explicit missing-product-interface
failures and no unittest errors/skips or integrity findings. The normal runner
propagated that failure; new guarded behavior, product image-lane report,
standalone import and later source/image/runtime stages were unreached.
No red evidence is attributed to those downstream assertions.

After classification and source release, the product module now frames actual
Secrets bytes and reconstructs existing artifacts through Core's descriptor
validation before admitting the full source contract. Canonical dependency/root
packaging and recipe select accepted Secrets0e0fa2c8. The recipe supplies the fixed
public path without a graph environment binding; historical descriptors and
image coordinates remain unchanged. Private bootstrap entries and service
entrypoint are unchanged; a separate public configuration entry documents source
startup. Root dependency/provenance/drift and cold-import assertions are extended.

The numeric source witness adds one tracked public artifact volume through
existing materialization/helpers, observes actual image ENV without injecting an
override, verifies regular0444/read-only content and preserves all existing
private0400/UID/data/provider checks. Same-service signed static/health reads use
separate in-memory keys, fresh120-second grants, bounded response accumulation
and missing/wrong-purpose denials. Existing ownership and reverse cleanup cover
the added volume/helper IDs; no new controller or process is introduced.

Standalone source mode currently exits2 with a204 handoff before any Docker call
or cleanup trap. One new package test protects that temporary admission using
only a command observer and bounded shell subprocess; existing published smoke
assertions remain. It and strengthened implementation-context assertions have no
separate red claim. Parent189 stays open for204 to restore source functionality.

Implementation and affected companions are prepared for full source/fixture
review. No green local gate, hosted run or implementation push has occurred at
this source checkpoint. Later tests must exercise the previously guarded laws
and full normal stages, with exact reviewed effect scope before execution.
Source configuration does not establish production delivery, OCI qualification,
public exposure or broader parent/held-runtime acceptance.

## First implementation gate and narrow coordinate correction

After North and Kepler source/fixture/plan review, implementation checkpoint
2640406 was published to the feature branch without a PR or hosted trigger.
The one authorized full owner gate stopped in root package discovery: 26 policy
tests passed, integrity inventoried 396 methods with 50 mock sites and zero
approved skips, and 45 of 46 root methods passed. One existing coordinate test
still expected the old canonical Secrets upstream commit, although this issue
intentionally adopts accepted source 0e0fa2c8. This was a missed fixture update,
not a collection or dependency failure; runtime behavior was not reached.

North and Kepler classified the failure. The correction changes only the
canonical upstream expected commit in that method, preserving historical
published source 68d0 and image digest 41aba assertions. No application source,
runtime fixture, gate, or effect scope changes. Product suites, the six target
laws, the temporary hold test, installed import and all runtime stages remain
unexecuted by this attempt. The owner independently observed no test resource
residue afterward; detailed environment and log evidence remain local.

The correction is pending exact review and a separately released full gate.
There is no green, hosted or merge-readiness claim, and no automatic retry.

## Corrected full owner gate

North and Kepler reviewed correction fa2c84b and carried the unchanged source,
fixture and full-command plan. After fresh preflight and a candid branch-only
checkpoint, one separately authorized full owner run passed: 26 policy tests
and all 396 package methods, with 50 inventoried mock sites and zero approved
skips. The six original product target laws and temporary source-hold law were
actually reached and passed. Coordinate, dependency, compile, image-definition
and installed-import checks passed as well.

The numeric source witness verified inherited image ENV, public artifact
delivery and read-only content, real signed static/health responses and denial
cases alongside the existing private bootstrap, UID, data, provider and cleanup
checks. Historical Secrets initial/restart smoke, configured CPK source smoke,
historical CPK image smoke, isolated root bootstrap and final residue audit
passed. The owner separately observed absence of its test runtime resources.

Root evidence remains bounded: mutation permission and external access are
explicitly unverified. Repeated acquisition was rejected as intended; that
expected HOLD is nonredispatch evidence. This does not establish public
grandparent acceptance, new immutable-image qualification or production
delivery. The earlier failed attempt is retained as failed evidence.

North accepted the local result, and Kepler independently reviewed the retained
output and reached laws. This evidence-only update changes no code, fixture,
dependency or gate, so the local green carries from fa2c84b. Matching final-head
hosted validation and Meridian's independent source/PR review remain required
before merge. The standalone source hold remains for #204; parent #189 stays
open until that restoration is accepted.
