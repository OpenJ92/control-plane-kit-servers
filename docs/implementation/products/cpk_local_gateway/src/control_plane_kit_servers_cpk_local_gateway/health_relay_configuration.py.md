# Explicit gateway management bindings

Source: `products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/health_relay_configuration.py`.

The immutable receiving map binds a name to exact Core target, runtime, V2
health declaration and HTTP origin. Its pure factory selects only the target's
control surface and declared provider port from a revalidated Core runtime
contract. It never enumerates ordinary edges, infers permission from runtime
membership, or selects application/SQL ports as fallback. Trusted composition
owns pinned Operations projection membership and hostname resolution (#181).

The closed JSON artifact is `gateway-health-targets` at
`/etc/cpk/gateway/health-targets.json`, mode0444, maximum131072 bytes, at most128
unique names and target identities. JSON depth is bounded by the product parser;
duplicate/nonfinite/unknown fields refuse. Only hostname-based plain HTTP origins
with an explicit port and no path/userinfo/query/fragment are supported. This
private-network transport assumes runtime DNS/network integrity; bearers remain
independently verified at receivers. Addresses are configuration, not HTTP errors.

The complete source runtime contract frames the exact selected trust, target and own-control artifacts,
requires matching workspace/gateway/runtime, and advertises health transit on
control8000. It creates no published image association and changes no historical
catalogue. Fixed configuration failures exclude candidate exception chains.

#182 completes the former #180 fragment. The factory now requires all three
artifacts, the actual gateway SDK liveness/readiness surface and NODE_CONTROLLABLE.
It replaces the two old independent HttpChecks with `VerificationContract()`;
the real SDK surface now supplies the managed observation obligation. Historical
image descriptors remain unchanged. No optional incomplete two-argument form is
retained. The complete returned contract enters actual Core compilation unchanged,
including verification and artifacts; its local-readiness obligation must gate
connector and subsequent authenticated-path/workload progress. The older #180
edge-free projection fixture remains only an endpoint-selection witness.

Validation: reviewed causal red and subsequent corrections are historical.
Exact source/test head ba9bc249 passed full owning CI35379205171:26 support and436
package tests plus existing runtime witnesses and owned cleanup.
[Evidence and limits](https://github.com/OpenJ92/control-plane-kit-servers/pull/216#issuecomment-5734352881).
That older evidence does not establish #182 or a deployed relay. PR218 records
the own-health source validation; #148 retains concrete bootstrap observation
transport and #181 retains production composition.
