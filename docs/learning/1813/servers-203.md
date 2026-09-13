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
policies. Add the separate public path environment/artifact and actual Secrets
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
This checkpoint is unexecuted: explicit missing-interface guards are expected
to fail while downstream laws remain unreached. Only the existing full owning
Docker-backed runner may establish red after exact effect review/release; no
custom selector or import/collection fault can substitute. Later source and
fixture review, full green and matching hosted validation are required.

Security/data: preparation creates no credentials, provider resources, runtime
mutation or public exposure. The target tests construct public values and later
inspect a cold import; real fixture authority/effects need separate review.
Product artifact production here is a pure value transformation, not authorized
production materialization or immutable OCI qualification. Those boundaries and
held runtime acceptance remain in their existing issues.
