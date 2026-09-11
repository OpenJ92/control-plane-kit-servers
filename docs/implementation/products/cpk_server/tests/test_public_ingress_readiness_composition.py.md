Source: [products/cpk_server/tests/test_public_ingress_readiness_composition.py](../../../../../products/cpk_server/tests/test_public_ingress_readiness_composition.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These two tests check the process factory's DNS resolver selection and bounded
configuration failure. A valid HTTPS endpoint constructs the adopted resolver
with an endpoint-hiding representation; a credential-bearing endpoint raises
the fixed BootstrapConfigurationError message without echoing that URL.

Neither test calls resolve or sends a DNS query. Fresh A/AAAA resolution, record
limits and transport behavior belong to the adopted Interpreters public_dns
owner, not this constructor witness. The test name's “refreshable” describes the
selected implementation, not a demonstrated refresh.

Related source: [server factory](../src/control_plane_kit_servers_cpk_server/server.py.md).
