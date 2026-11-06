Source: [installation_management.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/installation_management.py).

`DockerCpkManagement` is an optional pure composition input to the shared Docker
installation. It requires exact selected gateway and managed connector declared
contracts. Product images and canonical documents remain caller-selected; the
composer does not qualify an image or replace a declaration with a materialized
source contract. Each of three `DockerCpkConnectorControl` values binds its
receiver configuration to an ingress ID before the installation joins that ID to
the supplied connector node. API, website and management have distinct ingress
IDs, hostnames, connectors and role targets. The runtime selects its own gateway
and management ingress. Only CPK retains its explicit runtime access delivery.

`managed_children` instantiates the connector documents with the supplied public
control artifacts, then reads the actual configured server/connector blocks.
The product factory derives each relay origin from that block's node ID and
selected control-provider port. Its receiver workspace, runtime, node, socket
and full declaration must agree with the instance. All three server receivers
are required. The website has no control surface and gets no invented route.
Gateway self-control is included alongside the six other receivers. Product-owned
factories validate all three gateway artifacts against the same gateway target;
the selected declared document remains unchanged.

No keys/receiver identities are generated or rotated. No signer, runtime grant,
tunnel token, credential resolve, file/network I/O, scheduling or external action
is introduced. Ingress owners supply later token delivery. Existing SQL and HTTP
checks remain intact. A valid round-tripped graph does not resolve #190/#192's
executable independent-check/website waits and earns no live acceptance.

`test_installation_management.py` proves complete graph/codec and canonical
product identity, exact caller-supplied ingresses/receiver/trust preservation,
seven actual receiver routes with correct origins, CPK-only runtime access,
cross-wired/foreign/missing/conflicting inputs, and preserved native/standalone
behavior. Synthetic test documents are not qualified images. Owning validation
and independent review belong to PR #381.
