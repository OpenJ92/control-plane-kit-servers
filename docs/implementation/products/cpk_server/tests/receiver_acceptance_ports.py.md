Source: [receiver_acceptance_ports.py](../../../../../products/cpk_server/tests/receiver_acceptance_ports.py).

Issue #1912 effect boundaries. Compute stores exact request product/configuration
material and returns correlated replacement receipts with prior/current synthetic
allocation identities. It never reads desired values independently and never
writes Operations. Ingress and native observations are deterministic external
substitutes. External key lookup supplies ephemeral material only to the actual
Ed25519 signer using Operations-produced current grants.

SDK/gateway apps are constructed from installed material. Actual lifespans prove
serving readiness, with unhealthy state before and after lifespan. Local signed
SDK dispatch has no public resolver/client call; initial local readiness precedes
ingress/connector allocation. Supported external stages use the actual selected
DockerManagedHealthObserver and SignedGatewayHealthClient unchanged. Relay
routing dispatches to installed ASGI apps only, not arbitrary external addresses.
Returned health is decoded and folded by the actual owners, never manufactured.

This is source composition with named transport substitution, not a production
local observer, provider readiness or cloud/Docker replacement proof. Missing
receipt and key-material faults remain uncertain through the existing owners.

The ordinary `execute` arm explicitly refuses unregistered dispatch; only
`execute_with_authority` is usable. Unsupported operations fail closed. Exact
configuration-instance references received from Operations are retained for the
main witness's bounded owner reads, not interpreted as cleanup permission.
