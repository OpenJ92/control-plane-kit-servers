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

When registering gateway capability before an instance exists, use
`gateway_health_declared_runtime_contract()`. It declares the same control port,
health surface and transit protocol with three required configuration slots,
without receiver identities, public keys or route contents. A later
`ProductInstanceConfiguration` supplies the actual control, transit and routes
artifacts. CPK can bind this declaration at enabled startup; gateway process
startup and later health selection still require valid, matching actual material.
The declaration grants no authority and does not qualify an image.

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

#182 source validation: [PR218](https://github.com/OpenJ92/control-plane-kit-servers/pull/218)
records 26 support and 443 package tests green, including the seven new own-health
laws, plus the unchanged owning runtime witnesses and exact cleanup. Gateway is
one implementation family and one catalogue identity; its two roles do not
increase coverage counts.

## Supplied-input HTTP verification sample proof (#181)

This local stack additionally provides an explicit `create_app(http_sample_relay=...)`
composition. It is not selected by `main()`, does not change installed image
coordinates, and does not establish production grant issuance or admission.

The sample relay accepts `POST /cpk/verification/http` with no query and the
closed canonical JSON profile `cpk-gateway-http-verification-sample-request.v1`:

```json
{"profile":"cpk-gateway-http-verification-sample-request.v1","target_id":"<R.route_id>","request":{},"workload_credential":"<W>"}
```

`request` above stands for the actual Core request descriptor R. The gateway
authenticates its separate transit bearer G and compares both grants to R,
the independently supplied full gateway receiver identity, and the configured
workload route/target/declaration. Its only downstream operation is one
bodyless, queryless GET to the configured origin plus
`/__control/verification/http`, carrying W alone. The SDK owns W signature and
installed-check validation. The sender owns original-check result decoding;
an outer200 is not independently trusted sample evidence.

One absolute relay deadline covers admission and forwarding, capped at five
seconds and clipped to both credential expiries. Bounds are 32KiB of streamed
request bytes, 64/32KiB headers, 16KiB per credential, and 2KiB of successful
identity JSON response bytes. Redirects, proxies, retries, compression and
upstream diagnostic reflection are disabled. Fixed no-store outer failures do
not synthesize application outcomes. There is no durable replay guarantee.

The existing owning Docker runner has two explicit local proof selections:

```sh
./test.sh --http-sample-relay
./test.sh --http-sample-combined /path/to/reviewed/interpreters/checkout
```

The first credits a supplied test caller. The second exports the one reviewed
sender revision hardcoded in `scripts/http_sample_combined.sh`, verifies its
ancestry/new-source-only boundary and file hash, and mounts it read-only in the
ordinary test image. It records actual import provenance without changing the
selected package coordinates. Both selections preserve coordinate, policy and
integrity checks and use an isolated container with no external network or
host socket, followed by the existing health relay regressions.

The combined positive uses the actual sender, gateway and SDK with an injected
public DNS answer/outer ASGI transport and an asserted configured child origin
backed by ASGI. The SDK performs exactly one real numeric-loopback ready GET,
without a credential, and its response is decoded against the original check.
This proves a supplied-input byte/codec exchange, not public TLS/DNS, production
signing, current permission, native runtime registration or deployment. The
sender export, container and ready endpoint have owned cleanup; the local test
image is retained as a cache. The normal full gate is not replaced or credited
by these focused results.
