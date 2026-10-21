# Managed native connection composition

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
independently accepted that causal red. Native tests and fixture are unchanged
for this implementation; full green and later runtime/residue stages remain
pending. The target/dependency checkpoint notes in pin companions record those
earlier states, not a completed source or live acceptance.

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

Trusted process composition supplies capability-scoped borrowed Docker clients,
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
`DockerRuntimeClientSelector.select` to choose the unique client for the current
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
credential resolution, listener or cleanup ownership. Provider errors and
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
