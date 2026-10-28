# Managed native connection composition

## #293 owned policy and worker boundary

Trusted programmatic composition may now select an immutable Unix policy
instead of supplying a borrowed client:

```python
from control_plane_kit_interpreters.docker import DockerUnixSocketClientConfig
from control_plane_kit_servers_cpk_server.managed_health_placement import (
    DockerRuntimeClientSelector, DockerRuntimePolicyBinding,
)

policy = DockerUnixSocketClientConfig("/var/run/docker.sock", 5.0)
provider_clients = DockerRuntimeClientSelector((
    DockerRuntimePolicyBinding(workspace_id, runtime_id, authority_ref, policy),
))
# Pass this identical selector to ManagedHealthBootstrap and its native port.
```

The closed selector admits borrowed-client or policy bindings, keeps its
64-entry limit and rejects duplicate scope triples across both kinds. Current
active local authority remains required. Policy bindings do not supply private
gateway placement; a whole plan requiring local readiness still needs that
explicit capability. Public stages retain the existing signed NamedIngress route.

Selection uses the accepted client/clock-free qualifier. After current request
and authority checks, one synchronous worker constructs a lazy SDK wrapper from
the selected policy, invokes the unchanged observer and closes its owned wrapper
in finally. Original retained proof and material validation precede the first
SDK read, so invalid proof cannot trigger Docker construction or a version
handshake. The SDK owns failed-acquisition cleanup; closing a terminal wrapper
cannot close its raw handle twice. Existing borrowed clients are never closed.

Observer-classified UNKNOWN remains correlated to the current request. Escaping
ordinary failures and owned final-close failures become fixed unavailable;
cleanup failure cannot return a clean result. Cancellation propagates to the
caller without closing a blocked worker's client concurrently. The worker closes
when its call finishes; it cannot return late success to the cancelled caller.
Concurrent calls own distinct clients. This supplies neither a total deadline
nor a guarantee of cleanup after forced process death. Operations still owns
durable cancellation/result folding and retries.

Accepted Interpreters528fb206 supplies both fixed Unix acquisition and the pure
qualifier. Target run39622335625 reached26 policy/root60/connector80/gateway61
passing tests, then CPK491 with exactly13 missing-binding assertions and no
errors; all478 prior CPK methods passed. Kepler accepted that causal red. The
thirteen reviewed targets stayed unchanged for implementation. Full owning run
39623706350 passed26 policy/827 package methods and later normal witnesses;
Kepler FINAL6319834414 preceded accepted merge6b1bcd9. This is source acceptance,
not live qualification.

That #293 slice is programmatic composition. The [#294 startup format](managed-health-startup.md)
adds opt-in environment composition and one canonical policy across execution,
reconciliation and native reads; its source/gate status is recorded separately.
Neither slice implies image publication, retained deployment changes or
live225/291/284 acceptance.

## #291 forwarding implementation and evidence boundary

The selected cohort supplies Core's retained-image compiler, Operations'
retained-image profile and Interpreters' retained-image qualification. Targets
extend the existing genuine compiled fixture with a same-family image successor
and the original typed connector installation pair. These are composition input
values, not an admitted Operations history.

The discriminating target uses the actual unpatched observer and DockerSdkClient:
valid image proof must reach one unavailable-provider read and return UNKNOWN
correlated to the current effect. Missing proof or a separately valid original
installation for foreign material must return REFUSED before SDK I/O. Patched
observer assertions establish exact input identity only; no connected sample
or real native readiness is invented. Production now explicitly forwards the
same original request/receipt for retained-image and retained-content modes.
The qualifier, whole plan, current authority, current request correlation,
result conversion and single synchronous observer call remain unchanged.

The initial target checkpoint `3fae9dd` produced two intended forwarding
failures plus two stale provenance-expectation failures. After eleven current
source expectations were corrected, `f9becb96` run39600550494/job119223650616
passed 26 policy tests, root60, connector80 and gateway61, then ran CPK478
with exactly the two intended forwarding failures and zero errors. Kepler
independently accepted that causal red. Native tests and fixture remained
unchanged for that implementation. The later full gate39601338387 passed26
policy/814 package tests and its remaining runtime and residue stages. PR292 was
accepted as4731b951. Earlier target/dependency notes in pin companions are
historical, not live acceptance.

The existing synthetic native/ingress Docker image witness retains its actual
workload replacement/history/cleanup evidence. Final genuine connector and
public prepare/approve/execute/history A/B evidence remains mandatory jointly
under #291/#225; #284's native lifetime and same-native stop/profile laws remain.
Source integration cannot close those live gates or select live images.

## Existing process composition

This #181 slice connects the CPK process's existing native health port to the
accepted Interpreters `MANAGED_WRAPPER_V1` observer. Exact validation checkpoints
and acceptance status are recorded in [PR288](https://github.com/OpenJ92/control-plane-kit-servers/pull/288).
It does not qualify a deployed managed connector image or complete #181/#148.

Trusted process composition supplies capability-scoped borrowed clients or policies,
optional provisioner-owned controller placement, one reviewed canonical
connector document, and a UTC clock:

```python
from datetime import datetime, timezone
from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBootstrap
from control_plane_kit_servers_cpk_server.managed_native_connection import DockerManagedNativeConnection

native = DockerManagedNativeConnection(
    provider_clients=provider_clients,
    product_document=reviewed_connector_document,
    clock=lambda: datetime.now(timezone.utc),
)
health = ManagedHealthBootstrap(
    gateway_documents=(reviewed_gateway_document,),
    provider_clients=provider_clients,
    endpoints=provisioner_endpoints,
    native=native,
)
# Supply health as CpkServerBootstrapConfiguration.managed_health.
```

The document must match the actual registered declaration and graph metadata.
Registration alone does not qualify an image. The adapter reuses
`DockerRuntimeClientSelector.select` to choose the unique binding for the current
local Docker authority; this capability lookup grants no authorization. Optional
controller placement is required only for gateway-local readiness. There is
no ambient enablement, new registry, automatic image choice or support file.

Selection retains the original complete plan and performs no SDK, clock, binding
or secret read. The accepted interpreter qualifies fresh creation, its bounded
retained content-update shape or the exact retained-image ingress plan compiled
by Core. Servers does not reconstruct that plan or infer mode from a fixed
activity count. `WaitForHealthy` is unsupported by this managed
composition. Runtime execution rechecks the request, current authority and
selection before invoking the synchronous observer once through
`asyncio.to_thread`. The retained path passes the Operations-owned original
installation request and receipt unchanged. Missing proof remains a refusal;
it cannot become fresh-candidate evidence.

CONNECTED, DISCONNECTED and both correlated UNKNOWN forms become existing
Operations observations. Sample timestamp strings retain nanoseconds. REFUSED
remains a distinct no-sample value. Malformed, uncorrelated or exceptional
results raise a fixed composition failure for the coordinator's existing
read-failure handling. There is no helper, public probe or retry fallback.

Operations continues to own admission, installation history, structured result
folding and durable graph state. The adapter adds no transaction, mutation,
credential resolution or listener. Owned worker cleanup is described above;
borrowed client cleanup stays with the caller. Provider errors and
token contents are not returned.

`test_managed_native_connection.py` covers pure selection, result conversion,
unchanged retained provenance and the actual bootstrap → effect ports →
application factory → coordinator assembly. Its compiled topology and typed
input fixture is not a record of an admitted run. Recording-provider and
composition assertions do not establish live native connectivity. Existing
public CPK API, history, restart and teardown witnesses retain their explicitly
synthetic native stage; managed-image/live qualification remains separately
owned by #225/#284/#188.

Use the unchanged repository Docker `./test.sh` through the ordinary hosted
workflow and its existing prerequisites. No alternate runner, local socket
override or stop-profile bypass belongs to this slice.

## #341 admitted capability consumer targets (unvalidated)

Operations PR #2056 is accepted as `b08d87668b7208042ecd8dda68770ccb9cdf41c1`.
This checkpoint selects that Operations package while retaining Core4cc and the
previous SDK/Secrets/Interpreter cohort. Only the normal Docker suite can establish
that the actual installed cohort resolves; dependency text is not evidence.

The next consumer interface is a pure `bind_admitted(selection, workspace_id=...,
runtime_id=..., authority=...)` mapping on the installed selector. Its policy
binding retains the identical full `managed_target`, including revision. It does
not look up current assignments, construct clients, or grant authority. Existing
`select` remains current eligibility preflight. Native and bridge dispatch accept
the exact Operations `managed_target`; signed dispatch also forwards the original
`invocations` port. Configured-local endpoint reads enter `endpoint-observation`
and acknowledge before later signing. Public NamedIngress reads require no local
placement; this adds no placement supplier or process local-readiness support.

Targets exercise the pure mapping/refusal boundary, real SDK/native worker
acquisition and close for fresh/retained-image plans, actual signer/transport
control propagation, and configured-local admission/ack ordering. The public
assignment witness captures an actual owner selection A, grants B, and checks
current preflight B versus mapping of the original A. That capture is not claimed
to be an admitted run; Operations owns admission and its retained-history proofs.
No permission state machine is recreated here. Existing cleanup/cancellation,
original installation, scope and shape assertions remain unchanged.

These source targets have not run. Missing mapping/dispatch keywords should fail
before their deeper assertions; later PostgreSQL/public witnesses may be unreached
in the initial red gate. Report actual failures and reached boundaries rather
than predicting an execution count. Meridian reviews before the unchanged Linux
owning suite. Production composition remains unchanged at this target checkpoint.

### Consumer implementation checkpoint (green evidence pending)

The first target run40631080717 was mixed red: intended absent mapper/dispatch
interfaces and no-reselection law failed, alongside two stale expected Operations
pin assertions. The single expected-pin constant is corrected to acceptedb08;
Core4cc and exact assertions remain intact. North accepted the intended causal
red without another full run solely for fixture drift. See the owning #341 log.

`bind_admitted` now performs exact immutable catalogue mapping and retains the
original selection in the scoped policy binding. Native `qualify` preserves the
complete graph/product shape without current-assignment lookup; `select` still
performs eligibility preflight. Dynamic bridge/native dispatch requires the
owner target and maps it without reselecting. The existing worker still owns
lazy SDK construction, original installation proof, observation and final close.

Signed bridge dispatch requires a valid invocation port in dynamic mode and
passes it unchanged through the actual reader/signer/transport. Configured-local
endpoint selection/read is enclosed by endpoint-observation admission and outcome
acknowledgement. Denial/failed acknowledgement stops later signing. Cancellation
records unknown and stops the awaiting sequence; an already running thread may
finish later, so acknowledgement is not a claim of worker completion or cleanup.
A bounded thread test demonstrates this distinction; existing native worker tests
remain unchanged. Dynamic bootstrap readers also require invocation ports.

Dynamic policy capabilities still do not supply borrowed local placement. A
whole plan requiring local readiness is unsupported in that mode. Ordinary and
runtime/observer semantic profile registration, Cloudflare invocation forwarding,
trusted process configuration and installed-client query work remain separate
#341 connections. This checkpoint does not claim whole-issue or live acceptance.
