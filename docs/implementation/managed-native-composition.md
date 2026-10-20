# Managed native connection composition

This #181 slice connects the CPK process's existing native health port to the
accepted Interpreters `MANAGED_WRAPPER_V1` observer. Exact validation checkpoints
and acceptance status are recorded in [PR288](https://github.com/OpenJ92/control-plane-kit-servers/pull/288).
It does not qualify a deployed managed connector image or complete #181/#148.

Trusted process composition supplies the existing provisioner-owned placements,
one reviewed canonical connector document, and a UTC clock:

```python
from datetime import datetime, timezone
from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBootstrap
from control_plane_kit_servers_cpk_server.managed_native_connection import DockerManagedNativeConnection

native = DockerManagedNativeConnection(
    endpoints=provisioner_endpoints,
    product_document=reviewed_connector_document,
    clock=lambda: datetime.now(timezone.utc),
)
health = ManagedHealthBootstrap(
    gateway_documents=(reviewed_gateway_document,),
    endpoints=provisioner_endpoints,
    native=native,
)
# Supply health as CpkServerBootstrapConfiguration.managed_health.
```

The document must match the actual registered declaration and graph metadata.
Registration alone does not qualify an image. The adapter reuses
`DockerGatewayEndpointReader.select` to choose the unique client for the current
local Docker authority; this placement lookup grants no authorization. There is
no ambient enablement, new registry, automatic image choice or support file.

Selection retains the original complete plan and performs no SDK, clock, binding
or secret read. The accepted interpreter qualifies fresh creation or its bounded
retained content-update shape. `WaitForHealthy` is unsupported by this managed
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
