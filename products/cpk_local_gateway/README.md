# Gateway source health contract

The gateway owns two separate responsibilities on control port8000: its
own SDK health surface and the authenticated `/cpk/health/{kind}` relay.
Own readiness reports validated relay/control composition during the active
server lifespan. It requires no healthy downstream, connector or public ingress.
A relay failure remains a separate result and does not recursively break local
readiness. Liveness means the process can answer.

Production startup requires three selected public configuration artifacts:

- `gateway-health-transit` at `/etc/cpk/gateway/health-transit.json`;
- `gateway-health-targets` at `/etc/cpk/gateway/health-targets.json`;
- `gateway-control` at `/etc/cpk/gateway/control.json`.

The last contains the exact gateway target/runtime/declaration and separate SDK
surface-read/health-read public verifier families. Startup and source contract
composition cross-check workspace/gateway/runtime. No private signing material
is stored here. Missing, malformed or mismatched configuration prevents serving.

```python
contract = gateway_health_source_runtime_contract(
    selected_transit_artifact, selected_targets_artifact, selected_control_artifact
)
```

The complete source contract declares actual SDK liveness/readiness on control,
health transit, and all three exact configuration slots. It replaces its earlier
independent HttpChecks with the SDK management observation obligation; actual
Core compilation still requires gateway-local readiness before connector/path/
workload progression. This factory creates no published image association.

Existing public `/health/live` and `/health/ready` return only minimal process
status. Unready returns503. Protected SDK health routes require exact signed
workload-health credentials and return request-correlated Core outcomes;
public status is not equivalent to authenticated management-path evidence.
The relay separately verifies gateway transit and structural credential pairing,
then forwards only workload authority to a configured management endpoint.

Interpreters148 owns concrete local bootstrap observation,188 owns connector
truth, and181/1860 own production provenance, current authority and history.
No helper container, generic exec, extra socket recipient or private workload
fallback is introduced. Transitional probe wiring elsewhere in this product is
not a health fallback and must retire before parent1813 completes.

The owning gate is the existing Docker-backed `./test.sh` through ordinary PR
CI. Source/in-memory receiver tests and the SDK image recipe do not establish
qualified images, live TLS/DNS or cluster deployment. Historical published
product descriptors and catalogue coordinates remain unchanged.
