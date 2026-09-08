# Shared Docker installation value

`DockerCpkInstallation` describes one CPK Docker+Cloudflare process, one PostgreSQL
database for its four stores, and one dedicated Secrets process with retained
custody. `compose_docker_cpk_installation` returns an ordinary Core
`DeploymentTopology`. It performs no IO, secret resolution, authority admission,
workspace creation, or execution.

The composer belongs to the CPK product under Servers #153's explicit bootstrap
exception for cross-product composition. Its three small product-specific
factories declare existing process inputs through existing Core contracts. They
are not a general configuration or provisioning framework.

This example loads the repository's selected descriptors and creates only desired
values. The references must already have suitable external custody and explicit
admission before a driver executes anything. Example references are not secrets
and do not create credentials or grants in a running provider.

```python
from pathlib import Path

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.public_ingress import (
    IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget,
)
from control_plane_kit_core.runtime_authority import (
    RuntimeAuthorityAccessDelivery, RuntimeAuthorityAccessDeliveryKind,
    RuntimeAuthorityReference,
)
from control_plane_kit_core.secrets import (
    SecretProviderEndpointReference, SecretReference,
)
from control_plane_kit_servers_cpk_server import (
    DockerCpkInstallation, compose_docker_cpk_installation,
)

products = Path("products")  # This repository's product declarations.
codec = ProductDescriptorCodec()

def selected(name, filename="product.cpk.json"):
    return codec.decode_document((products / name / filename).read_bytes())

desired = DockerCpkInstallation(
    installation_id="child-a",
    workspace_id="parent-workspace",
    runtime_authority=RuntimeAuthorityReference("parent-docker"),
    runtime_access=RuntimeAuthorityAccessDelivery(
        RuntimeAuthorityReference("child-docker-access"),
        RuntimeAuthorityAccessDeliveryKind.LOCAL_DOCKER_SOCKET_MOUNT,
    ),
    cpk_product=selected("cpk_server", "product.docker-cloudflare.cpk.json"),
    postgres_product=selected("postgres_server"),
    secrets_product=selected("secrets_server"),
    control_credential=SecretReference("secret://parent/child-a/control"),
    postgres_password=SecretReference("secret://parent/child-a/postgres"),
    custody_root_key=SecretReference("secret://parent/child-a/custody"),
    provider_credentials_document=SecretReference("secret://parent/child-a/grants"),
    provider_client_credential=SecretReference("secret://parent/child-a/provider-client"),
    workspace_grants=(
        WorkspaceGrant("child-workspace", (PolicyScope.INSTANCE_WORKSPACE_READ,)),
    ),
    provider_endpoint_ref=SecretProviderEndpointReference("child-provider"),
    provider_bootstrap_credential_ref=SecretReference("secret://child/provider-bootstrap"),
    ingress=NamedPublicIngress(
        ingress_id="child-a-public",
        authority_ref=IngressAuthorityReference("parent-cloudflare"),
        target=PublicIngressTarget("child-a-cpk", "http-api"),
        connector_node_id="child-a-connector",
        hostname="child-a.example.test",
    ),
    connector_product=selected("cloudflared_connector"),
)
topology = compose_docker_cpk_installation(desired)
```

The example grants read access to exactly one child workspace. A deployment
client must explicitly select the additional scopes needed for its authorized
commands; the composer never expands these grants. A grandparent can manage many
workspaces, and an independent cluster can use the same client. Neither fact
implies authority over another cluster or its workspace.

For root-supplied ingress, replace `ingress` with
`ExternalInstallationIngress("https://root.example.test")` and set
`connector_product=None`. That endpoint remains an acquisition input. It emits no
graph-owned ingress or connector. Child deployment uses the existing
`NamedPublicIngress` and Cloudflare/cloudflared path.

Product image coordinates and provenance are preserved exactly. Variant identities
use a full SHA256 over canonical identity-free JSON containing the base descriptor
digest and variant runtime contract. Node identities derive from installation ID;
product identities derive from contracts. Identical contracts can be reused, and
changed PostgreSQL references change both verification/delivery and contract
identity. The final descriptor digest is calculated after assigning that identity.

PostgreSQL retains `postgres-data`; Secrets retains `provider-data`, scoped by
their node/workspace identities. The Secrets image defaults remain provider ID
`control-plane-kit` and database `/var/lib/cpk-secrets/secrets.sqlite3`. Equal local
provider IDs do not imply shared custody: each process has its own retained node
resource and admitted endpoint/credential references. Existing unbound custody is
rejected by the accepted Secrets source; this composer provides no adoption,
migration, reset, rekey, rollback or retry mechanism.

The CPK provider route uses the declared Secrets Docker alias, for example
`http://child-a-secrets:8081`. It does not reconstruct private hashed container
names or invent a provider socket. Bootstrap files use owner-read-only delivery;
the custody key and credential document have distinct accepted purposes. The
parent-delivered client credential reference and child-local bootstrap lookup
reference are deliberately separate.

`runtime_authority` selects the enclosing runtime. `runtime_access` is a separate
input for the eventual driver/client to admit for `desired.cpk_node_id` before
execution. Only the currently implemented local Docker socket delivery is
supported here. Merely installing Docker/Cloudflare software or composing the
graph does not grant authority or create a child's internal workspace/runtime.

The root `bootstrap.sh` driver, protected initial material, authenticated child
setup through public APIs, approval/execution, automatic ingress runtime proof,
and durable grandparent tracking after restart remain CPK #1778/#1779 follow-ons.
Source pins consume accepted Core/Interpreters/Secrets changes. Old published
image digests still identify their old source: this source change is not a
publication, retained installation repin, or installed-cluster acceptance.

The owning `./test.sh` exercises three product-owned composition tests using real
descriptors, graph compilation and the graph codec, followed by the repository's
existing source/live validation phases. No new test runner or provider fixture is
introduced.
