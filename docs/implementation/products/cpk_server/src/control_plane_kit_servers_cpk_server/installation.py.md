Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This pure product-owned composition turns DockerCpkInstallation values into
an ordinary topology. It selects canonical CPK Docker/Cloudflare, Postgres and
Secrets product documents, creates installation variants, connects all four
store requirements to one Postgres node, and optionally adds a named ingress
connector. It does not resolve credentials, admit authority, open providers,
execute a plan or establish a running database.

The installation requires explicit runtime selection and a matching local
Docker socket access delivery. Only the CPK instance configuration receives
that delivery; surrounding runtime authority and process permission are
separate values. Runtime access is independent of the product descriptor
identity, and later admission/execution must decide whether to deliver it.
Identifiers, ingress target/connector separation, unresolved secret references
and one-to-sixty-four unique exact-workspace grants are checked locally.

ExternalInstallationIngress accepts a credential-free HTTPS origin and owns no
ingress resources; its endpoint is not itself encoded into the returned
topology. NamedPublicIngress must target this installation's CPK HTTP provider
and select the connector product. Neither path creates DNS or a tunnel.

Selected documents must match canonical encoding, exact supported product
identity, ports, retained mount/lifecycle shape and expected base secret
deliveries. CPK process settings and Postgres user/database/verification are
also checked. This is a selected compatibility contract, not registry or
runtime attestation of the referenced image.

Variant identities hash the base descriptor digest plus encoded modified
runtime contract. Image coordinates, retained resources and lifecycle remain
from the selected product. CPK variants set provider routes/file locators and
Postgres identity, then replace secret deliveries with database/auth/provider
references. Postgres's password reference is shared by delivery and its
authenticated verification; Secrets uses file deliveries with path bindings
for custody key and provider credential document.

ControlAuthCodec closes single-operator and multi-principal input shapes.
Single mode configures the setup/control credential and declared workspace
grants. Multi mode delivers only the private principal-document reference for
control authentication, removes inherited single-mode public fields and
rejects incompatible auth secret inputs. Effective principals/scopes come from
that later-decoded private document; the installation grants still describe
setup requirements. The separate setup bearer remains required by bootstrap,
must differ from the principals document, and does not affect the multi-mode
topology when changed alone.

The returned values are desired state. Frozen dataclasses and canonical hashes
do not turn referenced material into admitted authority, enforce all nested
immutability, or provide cleanup/retry/history semantics.

Related source and evidence: [products/cpk_server/tests/test_docker_installation.py](../../../../../../products/cpk_server/tests/test_docker_installation.py), [products/cpk_server/tests/test_installation_control_auth.py](../../../../../../products/cpk_server/tests/test_installation_control_auth.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py), [products/cpk_server/product.docker-cloudflare.cpk.json](../../../../../../products/cpk_server/product.docker-cloudflare.cpk.json), [products/postgres_server/product.cpk.json](../../../../../../products/postgres_server/product.cpk.json), [products/secrets_server/product.cpk.json](../../../../../../products/secrets_server/product.cpk.json), [products/cloudflared_connector/product.cpk.json](../../../../../../products/cloudflared_connector/product.cpk.json).
