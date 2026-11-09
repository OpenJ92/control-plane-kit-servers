# Bounded #163 packaged gateway witness — preparation

Governing work: [Servers #163](https://github.com/OpenJ92/control-plane-kit-servers/issues/163).
North coordinates release, Linnaeus owns the owning selector/lifecycle action,
Rowan owns the reviewed gateway fixture interface, Meridian reviews independently.
This document prepares an action; it releases no build or runtime effect.

## Last verified boundary

At `872e508c2d66aafdd79f2db24b25efdff8ef9e86`, the owning source-only selector
passed28 support and83 gateway tests, including image-owner admission, bounded
readiness transport observations, real-main composition and fixture tests.
The saved source log SHA256 is
`ca5f392e76bd7ecc2bee8f4a091d57d4c0e670cb6637b34e9c24d3a4f58c89bd`;
[independent evidence PASS](https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-6746104948).
These are source ASGI/external-child-double results. No packaged gateway exchange
or approved deployment/history result follows from them. The earlier75/76 log
remains failed evidence; the corrected rerun does not rewrite it.

The existing `products/cpk_local_gateway/tests/packaged_sample_fixture.py` is
sufficient unchanged for the image exchange. Do not add a second signer, redefine
checks, or copy an Operations state machine. Lin's orchestration consumes this
interface and records actual images/lifecycles separately.

## Admission before the gateway build

Freeze the owning action's clean source revision and exact command for review.
Keep the frozen Secrets image action at1182fcc unchanged. The gateway action
must refuse missing/invalid prerequisites before reserving or building its image:

- Accepted CPK reference:
  `localhost/control-plane-kit-servers/cpk-server@sha256:4846a9005108e925149b2869214c3f32dbdbd4d4953159af532297081e80fe28`.
  [Accepted owned-network evidence](https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-6743638715).
- Separately qualified, retained Secrets reference:
  `localhost/control-plane-kit-servers/secrets-server@sha256:0d36584018d93305045631a1ee981d5a8850e16fd4532d765eb43a1a823dc095`.
  [North acceptance](https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-6746498542)
  binds producer1182fcc, run `cpk-secrets-image-smoke-cpk163-20261109-01` and
  raw receipt SHA256 `49168b24836f6b10281a0dd4fac4715d53d8f318680fcdb3f8598bf180ed6020`.
  Join the exact local digest/image
  to that action's public successful receipt and independent acceptance; missing,
  failed, uncertain, tag-only or substituted inputs stop before gateway build.
  Do not start a Secrets build from this action.
- Existing CPK PostgreSQL fixture reference:
  `docker.io/library/postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777`.
  This is its owned store prerequisite, not managed PostgreSQL product evidence.
- Exact retained controller ID and reviewed local context/daemon from the source
  action; source-only gate used controller
  `sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba`.
  Missing cache/daemon mismatch stops; no controller or borrowed-image acquisition.

Record `docker image inspect` identity/platform for the borrowed inputs and
recheck them after cleanup. Image reference syntax/existence alone is not
qualification. Required Secrets receipt facts include successful exit, exact
candidate reference, installed provenance, both signed pairs, custody/restart,
redacted logs, verified cleanup and retained candidate; North supplies acceptance.

Only after those prerequisites and a separate release may the action build ONE
gateway image from the clean tracked archive, unchanged gateway Dockerfile and
dependency coordinates, with a fresh owned tag, linux/amd64, source label and
build metadata. Record RepoDigest→image ID/platform association; retain candidate.
No push, catalogue/pin change, CPK/Secrets rebuild or second controller build.
Inspect installed Core976/SDKd61 origins and actual gateway source import inside
that candidate, dependency consistency, configured user `gateway` and resolved
runtime UID10005.
Source traversal shows those recipes already serve this contract; no dependency
upgrade is proposed. Any necessary public base/archive/PyPI acquisition belongs
explicitly in the later reviewed build release, never an implicit fallback.

## One fresh owned-network lifetime

Use one internal network without host publication. Fixed aliases:
`cpk-postgres:5432`, `cpk-source:8080`, `secrets-provider:8081`,
`gateway-source:8000`. Record actual container IDs, image IDs, aliases and mounts.
Fresh run and reservation-owner identities must precede allocation. Refuse name,
label or volume collisions; never adopt an existing volume because create returns
its name. Apply the existing exact-ID/run+owner/unreferenced cleanup discipline.

Reuse maintained launch inputs, not frozen action execution:

| Role | Required launch material |
| --- | --- |
| PostgreSQL fixture | Fresh owned data volume; existing CPK smoke's synthetic database/user/password and bounded actual SQL readiness. |
| CPK | `CPK_SERVER_MODE=execution-capable`, static development auth with synthetic credential, `CPK_RUNTIME_INTERPRETERS=none`, port8080; all four database variables equal `postgresql://cpk:cpk@cpk-postgres:5432/cpk`. Preserve the existing read-only root-workspace grant. |
| Secrets | Fresh, exclusively seeded master/credential/data volumes; existing provider UID10006 and actual entrypoint. Reuse the Secrets child bootstrap helper at its exact reviewed source coordinate, without mutating the frozen action. Mount bootstrap readonly at `/run/secrets/cpk-secrets`, data at `/var/lib/cpk-secrets`. No custody/restart rerun or application secret write is required to qualify gateway transit. |
| Gateway | Actual packaged default command on8000; own control and both transit configurations plus fixed target routes; no legacy probe authority is needed. |

The Seeds/bootstrap helper is a source prerequisite from the reviewed Secrets
slice; integrate/reference it explicitly in the new isolated action checkout.
Do not substitute arbitrary private credentials, copy old volumes/receiver IDs,
or launch the frozen Secrets image action as a nested build/qualification.

Start ONE retained-controller fixture process before the products. Inside the
owning gate it invokes:

```text
python products/cpk_local_gateway/tests/packaged_sample_fixture.py /fixture/public
```

This is the controller interface, not a released host command. Its source imports
need repository root, gateway src/tests, CPK src and Secrets src. Keep its five
private synthetic signers in memory from preparation through final requests.
It creates fresh public receiver IDs and files, then `prepared`. Copy no token
or private key into a product, report, build context or log.

Mount the rendered public0444 files individually, readonly, using actual target
paths and the product contracts' public environment:

| Fixture files | Product target directory |
| --- | --- |
| `cpk/control.json`, `cpk/http-samples.json` | `/etc/cpk/cpk-server` |
| `secrets/control.json`, `secrets/http-samples.json` | `/etc/cpk/secrets-server` |
| `gateway/health-transit.json`, `gateway/health-targets.json`, `gateway/control.json`, `gateway/http-sample-transit.json` | `/etc/cpk/gateway` |

Gateway's own control uses `CPK_WRAPPER_CONFIGURATION_FILE`; HTTP transit uses
`CPK_GATEWAY_HTTP_SAMPLE_TRANSIT_CONFIGURATION_FILE`. Both children require their
`CPK_HTTP_VERIFICATION_SAMPLES_CONFIGURATION_FILE`. V2 relay loads the two fixed
gateway health paths. Never replace public target/declaration/check bindings with
container name guesses or generic readiness assumptions.

Observe product readiness on the owned network, separately from host mapping;
use the maintained bounded readiness pattern and actual container state. Then
write `ready` once. The fixture's hard lifetime is240s, preparation wait120s;
the caller must bound completion and require actual helper exited/status0 plus
`samples.json`. No retry or new signer lifetime after failure.

## Packaged evidence and limits

The controller requires four exact original HTTP checks: CPK live/ready and
Secrets live/ready. Every response must decode canonically for the full original
request/check, PASSED/status200. Transit is an independent key/issuer from the
shared child workload HTTP verifier. Per exchange it mints fresh controls and
requires missing/foreign/wrong-purpose transit401, crossed selector/target/check403,
expired authority504 and foreign workload issuer outer502. The purpose-only
negative preserves the transit key/issuer/audience/type.

Separate generic V2 LIVENESS requests reach both child declarations; HTTP and V2
transit cross-use must401. The named HTTP ready check does not add generic V2
READINESS. No SQL health result, public ingress, provider authorization or durable
Operations truth is synthesized.

Keep these as separate receipt sections: source-test coordinates, built gateway
identity/provenance, borrowed child identities and prior acceptance, actual
packaged exchanges, process/network observations, redacted-log checks, cleanup
and retained-image checks. Overall success requires all applicable sections.
Stop on any failure/uncertainty and preserve which later sections were unobserved.

The packaged fixture reports only observed outer status for refusals;502 can be
transport/protocol failure, so forwarding and child refusal remain unobserved.
Its outbound credential/probe-count fields remain uninstrumented/not-observed.
The source-unit double's eight HTTP/two V2 call counts and complete workload-only
wire assertions must not be copied into OCI results as measured facts. Do not
claim approved child deployment, normal API execution/history, public login or
live installation from this isolated diagnostic.

Remove only exact owned containers, network, data/bootstrap volumes and private
fixture material after bounded redacted-log checks; preserve all borrowed images
and the retained gateway candidate. No broad prune or foreign resource cleanup.

## Small owner regression surface

Use the existing owning Docker test path to cover action admission/CLI boundaries
before release: missing/unqualified Secrets input must produce zero gateway
builds; exact borrowed image/daemon mismatch and run/volume collisions refuse;
one gateway build only; no borrowed/controller rebuild; helper failure and
cleanup uncertainty stay failed with no retry. Existing actual fixture tests
cover the signed wire boundary; preserve normal discovery and original assertions.
No packaged gateway execution result is claimed by this document.

## Implemented source preparation and current stop

Linnaeus's isolated action now enters through
`./test.sh --gateway-packaged-image INPUTS.json`, with the existing
`--gateway-packaged-source-tests` as its source prerequisite. Orchestration source
passed its Docker gate at872e508. This new pin/document/input-only checkpoint has
not been executed. No gateway build is released yet. The tracked
`products/cpk_local_gateway/tests/packaged_secrets_acceptance.json` now binds the
actual North acceptance, reference, raw receipt SHA-256 and run above. Admission
reads this pin from the immutable Git tree before Docker or run reservation.

Secrets qualification and North acceptance are complete. Review this new
source/pin and exact tracked input file before release. No environment override
or syntax-only comment can substitute for this pin. The Secrets producer and seed
source stay1182fcc unless a separate explicit supersession is reviewed; do not
silently align dependencies or the seed source.

The operator input is one nonempty JSON object, at most64KiB:

```json
{
  "schema": "cpk163.gateway-image-inputs.v1",
  "secrets_reference": "localhost/control-plane-kit-servers/secrets-server@sha256:0d36584018d93305045631a1ee981d5a8850e16fd4532d765eb43a1a823dc095",
  "secrets_acceptance": "https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-6746498542",
  "secrets_receipt": "/private/tmp/cpk-secrets-image-smoke-cpk163-20261109-01/result.json"
}
```

The exact input is tracked at
`products/cpk_local_gateway/tests/packaged_gateway_inputs.json`.
The real receipt must match the reviewed hash,
run/path, source1182fcc, controller/daemon, exact candidate reference, successful
exit, provenance, both signed phases, custody, exact-version/revocation persistence,
redaction, cleanup and retention. Receipt and input are copied once to a private
snapshot; the same validated receipt bytes are archived and rehashed before any
build. The pin's Git blob is also checked. Multiple/empty JSON objects and any
substitution refuse. The acceptance pin authorizes no execution by itself.

Exact proposed command, only after this checkpoint's independent review/release:

```sh
export DOCKER_CONTEXT=desktop-linux
export CPK_SERVERS_TEST_IMAGE=sha256:1c8b3fc348936b41bb51e530c9f192c360e3b4e53e7a9f7af6f41b7ba10e83ba
export CPK_RECEIVER_DAEMON_ID=d23d00aa-b281-448d-bc95-c8e47efeeea2
./test.sh --gateway-packaged-source-tests && \
CPK_GATEWAY_IMAGE_RUN=cpk-gateway-image-smoke-cpk163-20261109-01 \
CPK_GATEWAY_IMAGE_TAG=localhost/control-plane-kit-servers/cpk-local-gateway:cpk163-relay-20261109-01 \
./test.sh --gateway-packaged-image products/cpk_local_gateway/tests/packaged_gateway_inputs.json
```

Run from the clean frozen commit containing this pin and input. Source tests must
pass there before image mode;872e508 is prior source evidence, not a result for
this new pin checkpoint. The image selector first performs non-Docker admission, retains the existing
coordinate/support/integrity checks, and then revalidates the image action's
immutable inputs. It does not run or rebuild the frozen Secrets action.

Only the gateway's normal unchanged recipe may acquire public python:3.12-slim,
Core976/SDKd61 archives and normal PyPI packages (FastAPI, PyJWT crypto, uvicorn,
httpx<1 and psycopg binary) during its single linux/amd64 local build. Every
borrowed image must already be cached on the fixed daemon; no CPK, Secrets,
PostgreSQL or controller acquisition/build is allowed. Native metadata checksum
requires sha256sum or shasum; neither absence nor denied Docker access permits
install/fallback/repair without a new boundary. These equivalent utilities hash
public evidence only; host Python is never used.

The implementation follows the setup order above: build/provenance first, fresh
owner-labelled network and four local optionless volumes, exact1182fcc exclusive
Secrets seed, PostgreSQL SELECT1 readiness, THEN the existing signer CLI. Eight
public product files plus its prepared marker appear before the three default
product processes start. This keeps build/DB initialization outside the fixture's
120-second wait. A socket-free readiness controller verifies both child ready200
and gateway unsigned protected-route401. Actual images/default arguments, PID1
UIDs10001/10006/10005, aliases, no host ports and exact read-only public/private
mounts are checked before ready is signalled once. Parent completion is90polls;
helper must actually exit0 with its original result. No signer restart/retry.

Resource ceiling: one internal network, four native local volumes (PG data,
Secrets bootstrap/client/data), PostgreSQL, one CPK, one Secrets, one gateway,
one signer and transient provenance/bootstrap/readiness/log controllers. Every
allocation has an attempted role/cidfile and fresh32-byte reservation owner.
Only bootstrap runs as root for protected fixture file ownership; the three
products retain their numeric runtime users and drop capabilities with
no-new-privileges. No Docker socket or host publication is used. Root bootstrap
and log inspection have network none. PG uses its unchanged official image
entrypoint and the original isolated synthetic database settings.

Bounded private logs for PG/CPK/Secrets/gateway/signer retain producer status
separately. A no-network inspector rejects failed/oversized retrieval, Bearer or
compact JWTs, private-key markers, database URLs and actual synthetic private
seed values, without echoing content. Known private log files are deleted even
on uncertainty. Public snapshots are limited64KiB and exclude environment;
they retain process state, image/arguments, aliases, ports and mount metadata.

Cleanup only removes recorded attempted IDs or reserved exact names with matching
run AND fresh owner, verified unreferenced local volumes and the internal network.
Unexpected same-label or wrong-reservation resources stay untouched and fail
cleanup. Input snapshot removal happens before final result serialization; failure
marks cleanup unverified/nonzero. Borrowed refs/IDs/platform and gateway candidate
are rechecked and retained. No prune, automatic repair or image deletion.

Prepared owner tests exercise null/unqualified pins, unrelated valid-format
acceptance comments, substituted reference/receipt bytes, multiple JSON objects,
wrong daemon/image, volume collision, failed Git read with empty stdout, a foreign
reservation, helper failure and failed cleanup readback. They use actual owning
scripts with finite fake CLI responses inside the Docker source suite. Separate
log tests enforce bounded non-reflecting redaction. These passed in the83-test
source gate at872e508; no packaged result follows. Source failure, missing accepted Secrets input,
receipt/hash or cache drift, apparatus failure, process/relay failure, timeout or
uncertain cleanup stop without retry. North owns the next release.

## Pre-build metadata stop and bounded correction

The released image invocation at04bbd42 stopped before reservation/build:
[durable stop](https://github.com/OpenJ92/control-plane-kit-servers/issues/163#issuecomment-6747382362).
No gateway build was consumed or relay/runtime result earned. North subsequently
released read-only metadata diagnosis and this eligibility-preserving correction.
On the fixed daemon, PG/controller have no Labels field; canonical and familiar
PG references both resolve to ID
`sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777`,
and Docker reports RepoDigest
`postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777`.

The corrected inspection selects only required fields by role. PG/controller
do not access Config/Labels/Env. Product projections read only required labels;
missing/malformed/mismatched required labels still refuse before reservation.
CPK keeps exact digest/Linux/amd64/producer checks; Secrets additionally keeps
accepted run/receipt owner. PG accepts only the two exact equivalent repository
spellings with its full unchanged approved hash; controller keeps its exact ID.
Failed inspection reports the bounded role without reflecting Docker stderr.
Regression cases cover label-free permissive roles, both PG spellings, wrong PG
digest, failed inspection and missing/malformed/wrong protected provenance.

This correction changes no pin, input, production recipe, fixture, network,
credential or cleanup authority. It is unvalidated source until its owning
Docker suite passes. Exact-source independent review and North's next release
are required before another image-phase invocation; the failed one is terminal.
