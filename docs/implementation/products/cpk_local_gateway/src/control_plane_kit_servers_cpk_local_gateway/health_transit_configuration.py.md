Source: [health_transit_configuration.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/health_transit_configuration.py).
Maintain this companion alongside its source.

This product owns `cpk-gateway-health-transit-configuration.v1`, a public but
integrity-sensitive snapshot: configured workspace, gateway node, runtime,
issuer, exact gateway health-transit purpose and one to sixteen public keys.
Audience is derived as `gateway:<workspace>:<gateway>`. Workload target,
declaration, health kind, attempt and time are not startup trust.

Issuer uses exactstr plus pinned Core95452249's
`_node_control_public_wire.reference_violation`, including its endpoint and
credential-envelope rejection. The direct private-helper dependency is an
explicit compatibility risk: future Core pin upgrades must verify this
contract. It avoids a copied validator, fake context or public facade; no new
Core export is introduced. Syntax-only acceptance would admit issuers for
which Core cannot construct a health grant.

The sole decoder accepts at most16384 UTF8 bytes with closed field sets,
duplicate-key/nonfinite/type refusal and structural depth8. Public keys use
exact Core identities, parsed Ed25519 SubjectPublicKeyInfo PEM, a coarse512byte
early PEM bound and canonical representation. Duplicate IDs or material
fingerprints refuse; immutable keys sort by ID. Alternate PEM wrapping cannot
manufacture distinct material identities. Configurations expose a redacted repr.

The encoder revalidates the configuration and decodes its own bytes before
creating the fixed `gateway-health-transit` JSON/0444 artifact at
`/etc/cpk/gateway/health-transit.json`. The private artifact entrance validates
the exact slot, content bound and Core descriptor digest before using this same
decoder. `source_digest` is provenance only, never semantic authentication.
The verifier factory consumes those actual selected bytes; no second supplied
trust assertion or hash substitutes for decoding.

Expected malformed-input/crypto failures become a fixed configuration error
raised outside the catch context; exception attributes/text/repr carry no
candidate. BaseException is not caught. Parsing is bounded trusted in-process
code, not a sandbox. No file is opened, no secret is resolved and no state is
written. The configuration profile's meaning must remain stable for pinned
product descriptors and later Operations recomputation.

This source contract is not a mounted-file or gateway-process adoption claim.
Servers208 owns real composition adapters;180 owns later receiver wiring and
relay;1857 owns exact selected product/graph admission. Existing probe products,
catalogue/image descriptors and their configuration stay unchanged.

Governing targets: product `test_health_transit.py`, especially actualA/B fresh
artifact digest, overlapA+B, distinct16/17keys and valid16384/16385bytes. Native
red at8b05ff4 reached only missing-module guards; source green remains pending
at this implementation checkpoint.
