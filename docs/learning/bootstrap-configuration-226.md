# Bootstrap configuration delivery

Governing [Servers226](https://github.com/OpenJ92/control-plane-kit-servers/issues/226),
parent181, prerequisite225. Base `e8e770167dbc0cae69a6c376c829e96894145b42`.

## Decision log

- Chosen shape: compile installation to graph, project complete configuration
  values into the existing root plan, then use SDK materialization/digest/mount
  operations. The graph already owns bytes, modes and targets. Thirty source
  lines connect those existing owners without another execution engine.
- Important shape: `configuration_files` entries contain `name`, `target`,
  `artifact` and `sha256`; acquisition uses
  `DockerSdkConfigurationMount(artifact, name)` only after verified delivery.
- Alternatives rejected: manual live mounts, broadening0400 to0444, a new SDK
  ownership interface, source-image substitution or bypassing managed-plan guards.
- Laws: pure deterministic projection; exact saved-plan binding; configuration
  occupancy refusal; root-owned0400/nonroot refusal before acquisition; pending
  before materialization; digest/mount failures stop recipients; no redispatch.
- Target evidence: `7e97de082dd3ad9a1215ba80ba868fc172b217c1`, Meridian TARGET PASS
  PR227 comment5805213448. Ordinary CI35938374148 ran296 CPK methods and failed
  exactly seven missing-projection assertions across six new methods, with no
  errors. Application implementation follows that immutable target checkpoint.
- Validation: source checkpoint, green and independent source review pending.
  Existing real launcher witness now checks inert0444 configuration on numeric
  CPK/Secrets recipients, exact bytes/mode/read-only mounts and owned cleanup.
  Historical product images prove delivery only, not current-source startup.

The first source gate35938626768 exposed stale exception identities in the new
fixture: earlier composition tests evict product modules, while the fixture held
its collection-time bootstrap module. All five fault subcases reached their
intended runtime refusals, but `assertRaises` compared against the old class.
The fixture now imports the current bootstrap API in `setUp`, matching the
existing root tests. Exception types and all behavior assertions are preserved;
no application or shared harness change was needed. The target-red runs establish
missing projection, not independent proof of these previously masked branches.

## Security, data and history

Public configuration is secret-free but integrity-sensitive. Existing secret
delivery and authenticated initialization are preserved. No new endpoint,
credential or provider authority is introduced. Config volumes use the existing
conflict/ownership rules. Private receipts retain pending intent before writes,
verified digest observations afterward, and container IDs before mount checks.
Exceptions do not expose provider bodies. SDK archive/mode behavior is reused;
the real recipient witness prevents treating byte digests as permission proof.

Docker effects have no group transaction or automatic compensation. Existing
local state locking/atomic receipt writes apply; independent state directories
are not a distributed lock. Any receipt prevents apply reentry. Exact owned
volumes remain inspectable on HOLD and follow existing cleanup. No adoption,
repair or implicit retry is added.

## Handoff

Objects and transformations remain graph → inspectable plan → SDK effects →
private acquisition observations. Root bootstrap is the external acquisition
exception, not Operations lifecycle history. This slice supplies a prerequisite
for181's current-source product-input/image adoption.1860/148 still own trusted
managed execution and concrete bootstrap/health effects;225 must prove the real
authenticated API deployment, health and desired-empty teardown. PR224 remains
paused and unmerged. No live/provider/image effects are released here.
