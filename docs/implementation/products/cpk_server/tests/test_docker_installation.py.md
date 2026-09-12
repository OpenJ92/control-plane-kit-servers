Source: [products/cpk_server/tests/test_docker_installation.py](../../../../../products/cpk_server/tests/test_docker_installation.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests build installation values from real selected product documents and
compile them through Core. They witness pure composition, not live Docker,
secret delivery or a grandparent/child deployment.

Named ingress yields CPK, Postgres, Secrets and connector nodes, with four
store edges to the same database. Assertions tie provider bootstrap locators,
database/auth secret references, custody file intents/modes/path bindings and
Postgres verification to the declared inputs. Generated product identities
change with runtime-contract changes while image, retained mount and lifecycle
values are preserved.

Permission cases assert that only CPK declares the matching runtime access
delivery, at both instance configuration and compiled-node boundaries.
Codec roundtrip retains it; removal changes the graph while preserving the
product document/metadata and omits empty permission fields. This proves
desired permission representation, not Docker socket access or authorization.

Repeated composition and codec roundtrip are stable. Separate installation
identities produce disjoint node IDs, unchanged contracts can reuse a variant,
and a changed database secret reference changes the relevant variant identity.
External ingress produces three nodes and no graph-owned ingress.
Negative cases reject raw credential strings, empty/wildcard grants, missing
or contradictory ingress/product input, invalid IDs and mismatched authority.
These selected laws do not audit every product codec or bootstrap effect.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py), [products/cpk_server/tests/test_installation_control_auth.py](../../../../../products/cpk_server/tests/test_installation_control_auth.py), [products/cpk_server/product.docker-cloudflare.cpk.json](../../../../../products/cpk_server/product.docker-cloudflare.cpk.json).

The runtime-material composition regression continues from the actual installation composer through Core compilation into public Operations translation. Exact composed variant documents provide registration identity/digest; a minimal public record context supplies pinned inputs without dispatch. The second case re-instantiates only the Secrets child with changed reference configuration while asserting descriptor bytes unchanged. Full ordered delivery-tuple equality detects both duplicate slots and retained default references. These cases prove dependency composition, not secret resolution, grant authorization, Docker execution or historical failure cause; those remain with their owners.
