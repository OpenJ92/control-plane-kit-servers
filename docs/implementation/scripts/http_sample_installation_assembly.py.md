Source: [http_sample_installation_assembly.py](../../../scripts/http_sample_installation_assembly.py).

This is the unfinished complete-child assembly checkpoint for #181/#163. It
does not execute the approved program and is not source-live, admission,
signed-sample, or durable-history evidence. Its opt-in owning runner command is:

```sh
CPK_SERVERS_TEST_IMAGE=cpk181-grandparent-source:local ./test.sh --http-sample-source-assembly \
  /private/tmp/cpk148-native-core-054e /private/tmp/cpk1815-http-sender \
  /private/tmp/cpk148-native-http-sample
```

The shell archives exact Core054e, Operations71db and Interpreters2e2 source.
The controller has no network, Docker socket, writable root or live provider.
Temporary commissioning material lives only in its owned tmpfs directory;
exports are removed and their absence checked. Root commissioning uses private
files inside that owned tmpfs directory; the additional sample keys stay in
memory. Neither appears in output. Package pins and installed products are unchanged.

Test context and dry run

- Strengthened: the existing installation-management source sample-artifact law
  preserves the original CPK contract. This checkpoint additionally checks both
  original live/ready checks, all four PostgreSQL edges, the original password
  reference/intent, and runtime authority delivery. No checks are narrowed.
- Isomorphic: production `compose_docker_cpk_installation` still owns the full
  installation shape. The existing `InstallationManagementTests` supplies only
  authored fixture inputs; no test service, returned invocation or accepted
  Operations record is reused.
- Non-executable-scaffold: the remaining actual dynamic factory, isolated
  PostgreSQL history, real registered adapters, provider doubles, signer, SDK
  and public readback assembly is not implemented by this script. No target
  green or approved-run receipt is claimed.
- The script must report a genuine review-blocked plan if the preserved SQL
  readiness check remains unsupported by the fresh HTTP sample profile. Exit0
  means the pure structural assertions ran, not that `plan_ready` is true.

Chosen shape and limits

The child uses the complete installation composition and its actual CPK source
contract, including the four database requirements and ordinary `postgres.password`
delivery. Only that CPK child's HTTP checks receive sample configuration. The
existing installation API currently admits the health-only gateway declaration;
the fixture labels an explicit post-composition graph/document extension for
sample trust. It does not change that public API or pretend this is already a
supported installation input. Other products, SQL checks and ingress obligations
remain present. This may expose more than one blocker; each must remain visible.

Security: no new production route, authority, external exposure or provider
mutation. The diagnostic emits bounded classifications and authored identifiers,
not secret values, tokens, full descriptors, provider bodies or exception text.

Data/history: no Operations schema, session, plan record, approval, execution,
secret-use row, observed state or current pointer is created. Real approved
execution must obtain those facts through normal owner services, then join the
actual SDK answer to public history using `http_sample_execution_acceptance.py`.
No retry/cleanup of deployed resources is needed because no deployment runs.

Handoff: identify preserved non-HTTP obligations before attempting the first
runtime command. Resolve any source-owner plan refusal through normal review;
do not drop the SQL check, add an external database to evade it, or fabricate a
positive history record. Separate component passes remain separate evidence.

The existing pure `root_complete_fixtures.complete_input()` removes its owned
commissioning directory before returning public artifacts. It cannot supply
that original health-signing private material to an execution. The eventual
execution fixture must own those material inputs for its full lifetime, or
explicitly author and revalidate new desired trust. Reusing these pure public
values does not make a completed runtime fixture.

Observed checkpoint

The owning command completed its 28 support tests and pure structural assertions
with exit0. The resulting eight-node/three-ingress graph is valid, but
`plan_ready=false`: `unsupported-change` reviews remain for `root-a-postgres`
(the original `installation-postgres-ready` SQL check) and `root-a-secrets`
(its original `live`/`ready` HTTP checks, without sample trust in this CPK-only
slice). No review was approved or removed. Operations commands, provider calls
and completed runs are all zero. This is a real planning refusal, not a completed
execution or accepted #163 evidence.

Terminal log: `/private/tmp/cpk181-source-assembly.log`, SHA256
`23431063dc78bc01c20c00b3f90f233f3be96725fe8a053448576fd198ef860f`.
The first diagnostic projection failed on a missing Core root export; imports
were corrected to the public planning module before the successful validation.
Its log remains `/private/tmp/cpk181-source-assembly-first.log`, SHA256
`5ae5f9b9d080907c276287db18e4128e6208e39233b9c75b4111b5ebab362cf3`.
No runtime command was retried. Both invocations removed their source exports;
their controllers were disposable and the local test image remains build cache.
Meridian independently verified the terminal log hash and accepted this pure
diagnostic while holding the #163 execution claim. Neither review targets the
CPK child itself; the other two obligations and commissioning material lifetime
must be resolved before the actual approved run.

Secrets companion and concrete child-input handoff

This belongs to existing [#388](https://github.com/OpenJ92/control-plane-kit-servers/issues/388)
and [#378](https://github.com/OpenJ92/control-plane-kit-servers/issues/378), not a
second demonstration or a global restriction on subset receivers. Their existing
[product-author trace](https://github.com/OpenJ92/control-plane-kit-servers/issues/388#issuecomment-6693730999)
and [recipe handoff](https://github.com/OpenJ92/control-plane-kit-servers/issues/378#issuecomment-6693748702)
already distinguish the two responsibilities. The current source has the generic
binding/artifact functions; the proposed full-pair author and four-response
witness are not implemented on this checkpoint and #387 remains held.

The missing public value for `root-a-secrets` is a full
`HttpVerificationSampleReceiverConfiguration` joined to its independently
selected existing V2 receiver, not a second receiver or a port-inferred target:

| Input | Exact source-checkpoint requirement |
| --- | --- |
| Receiver | Existing `root-workspace` / `root-a-docker` / `root-a-secrets` / `control` target, same receiver ID and declaration identity as its selected control artifact. |
| Original checks | `live`: `/health/live`; `ready`: `/health/ready`, both named socket `control`, original port8081. Preserve expected200, timeout5s, interval1s, maximum10 attempts and evidence16384 bytes. |
| Check bindings | Both exact ID/digest pairs, derived with selected Core's `http_verification_check_digest` on the original typed checks. Repeating `ready` or a subset is insufficient for this plan. |
| Sample verifier | `WORKLOAD_HTTP_VERIFICATION_SAMPLE`, explicitly supplied issuer and Ed25519 public keys, with provenance to the active registered key selection used by Operations. No inferred or fixture key may stand for that selection. |
| Companion artifact | Product-owned `secrets_http_sample_configuration_artifact(control, configuration)`, ID `secrets-http-samples`, path `/etc/cpk/secrets-server/http-samples.json`, canonical JSON, read-only. |
| Runtime contract | `secrets_source_runtime_contract(original_control_artifact, sample_artifact=companion)`, preserving original verification, retained data, control and port metadata. |
| Concrete recipe | #378's actual child-product input must include that document and sample environment selection through ordinary composition/artifact delivery. Merely showing that the composer preserves supplied artifacts is insufficient. |
| Gateway route | Existing `root-a-secrets` target/declaration at `http://root-a-secrets:8081` remains selected from the actual managed installation routes. Transit public trust belongs to the same gateway target; it does not replace the workload verifier. |

The original product's independent canonical Secrets digest expectations recorded
and reviewed on #388 are `5911cb3dce76dacd9bdea52d33cc07fb8879fb6318a826cf64653316ae3920b7`
for live and `9168b2fe37d83e63062a3d22be950b90b3be48062755744ff70879c5c0538b1f`
for ready. Future code must still derive these from the actual original checks
using Core's canonical function. Sorted Python JSON with integral float spellings
is not the wire identity. This handoff adds no independently executed digest or
four-listener evidence.

#388 owns the pure product full-companion author and separately correlated
CPK/Secrets live+ready source-listener proof; it does not choose registered trust
or perform the grandparent run. #378/North own the concrete non-smoke caller and
approved public trust provenance. Operations1815 owns current key/use authority,
permission admission and history. The real native sender resolves signing
material only through the returned grants. The SQL review remains independent
even when the Secrets companion is supplied; this handoff does not unblock or
waive it.

Fixture signing material lifetime is a separate test apparatus input. Two pure
fixtures intentionally discard private material: `complete_input()` deletes its
commissioning directory before returning public artifacts, and
`InstallationManagementTests.setUp()` keeps only `AuthoredMaterial().public`.
Consequently neither its original workload verifiers nor the added fixture
sample/gateway public keys establish an available signing path. An execution
fixture must own the matching synthetic private inputs until test completion,
with the actual resolver/provider boundary, ordinary registrations and grants,
then verify exact owned cleanup. Keeping those fixture inputs alive is not a
request for live keys, a production credential change, or evidence that the
installed service lacks credentials. Public companion authoring must never read
private material or mint a grant.

Next validation remains the same eight-node graph: author/select the real full
Secrets companion through those owners, preserve every existing check, recompile
and report all remaining reviews. Only a genuinely executable and normally
approved plan may reach the real registered execution and history join. No new
execution, live/provider call, pin adoption, cleanup of retained resources or
#387 acceptance is authorized or claimed by this documentation.
