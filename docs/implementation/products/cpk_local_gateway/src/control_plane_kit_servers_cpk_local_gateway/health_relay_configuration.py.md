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

Validation: reviewed target tests and causal missing-interface red on PR216;
implementation is unvalidated pending the authorized ordinary Docker CI.
