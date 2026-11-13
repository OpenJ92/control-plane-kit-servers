# Retained managed connector qualification

Issue #356, parent #191, consumer #225. A fixed mode in tests.yml composes current
orchestration with a separate clean historical owner checkout at cc1b8d8. Its
fixed input is the already-published 812262 repository digest. It does not repair
the failed historical release or publish an image.

`prepare` initializes a private attempt outside both checkouts and validates the
actual daemon before registry login or acquisition. Engine version and commit
must satisfy the historical witness's reviewed default-stop pairs. A hosted
runner label is not proof. SDK version and actual container stop configuration
remain the unchanged witness's responsibility. No timeout overrides or Docker
installation are performed.

`run` repeats admission, writes pull intent, pulls once, and binds exact
RepoDigests membership to the observed local image ID/platform/revision. It
invokes the historical `test.sh --managed-connector-controller`, then
`--managed-connector-candidate`; the controller build uses its existing public
base/apt/pip acquisition and inherited transport retries. There is no connector
build, push or retry loop. Daemon identity and image association are checked
again. The existing owner retains its exact-owned cleanup semantics, including
failure cleanup and uncertainty after interruption; this helper never prunes or
deletes Docker resources itself.

The new `cpk.cloudflared-retained-qualification.v1` result is closed and at most
64 KiB. It distinguishes orchestration and owning source, hashes source and
private receipts, and projects only fixed outcome fields. Raw command output is
private. Only result.json is uploaded for 30 days, including failure or running
records left by interrupted work. `running` is incomplete evidence. Runner loss
can prevent upload entirely. A failed projection preserves an existing primary
failure; it cannot turn a failed run into success. Missing cleanup is never
verified. Images remain in the ephemeral runner cache until runner disposal.

Security: contents/package reads only; registry credentials are owned by the
login action and never passed to product containers. The historical qualification
controller has Docker socket authority and creates three network-none witness
children. No real tunnel, token, ingress, provider mutation or live deployment is
part of this workflow. Source review does not authorize dispatch.

The existing registered tests.yml workflow supplies the invocation route at the
reviewed orchestration ref. Its boolean retained_managed_connector input defaults
false. Only explicit workflow_dispatch with that input true selects this job and
excludes the ordinary full suite. Conflicting wrapper/root selections are refused
before checkout/login/acquisition. Push, PR and ordinary manual runs preserve
their existing full-suite/root/wrapper behavior. Qualification has a separate
concurrency group with cancellation disabled; default runs retain their existing
group and cancellation behavior. No standalone workflow registration, default
branch promotion, or trigger experiment is required. A future execution release
must bind the reviewed ref and confirm workflow availability through metadata.

Tests in test_managed_release_retained.py exercise the additive boundary using
synthetic command results. The maintained `--managed-connector-release-tests`
route discovers them without new runner code. That source gate runs with no
network or Docker socket; its success is not retained-image qualification.
