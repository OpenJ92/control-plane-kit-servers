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

The source runtime contract frames the exact selected trust and target artifacts,
requires matching workspace/gateway/runtime, and advertises health transit on
control8000. It creates no published image association and changes no historical
catalogue. Fixed configuration failures exclude candidate exception chains.

This helper is a relay source-contract fragment, not sufficient for managed
bootstrap planning. It has no gateway own protected readiness surface. Selected
Core `management_compiler._selected_surface(gateway=True)` / `_pin_path` requires
that surface and correctly refuses this fragment. Existing Servers #182 (which
depends on #180) owns truthful SDK gateway self-health. #181 composition and
Interpreters #148 bootstrap transport must wait for that owner; no invented
surface or dependency cycle is introduced here. The edge-free projection fixture
supplies a separate synthetic gateway readiness surface to prove endpoint
selection only; it does not prove this helper's bootstrap eligibility.

Validation: reviewed causal red and subsequent corrections are historical.
Exact source/test head ba9bc249 passed full owning CI35379205171:26 support and436
package tests plus existing runtime witnesses and owned cleanup.
[Evidence and limits](https://github.com/OpenJ92/control-plane-kit-servers/pull/216#issuecomment-5734352881).
This does not establish managed bootstrap or a deployed relay.
