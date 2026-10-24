# Shared Docker installation value

For explicit first-root public read trust, see
[offline root commissioning](root-commissioning.md). Private commissioning
custody stays separate from installation material; it is never a service mount.

`DockerCpkInstallation` describes one CPK Docker+Cloudflare process, one PostgreSQL
database for its four stores, one dedicated Secrets process with retained
custody, and an optional website. `compose_docker_cpk_installation` returns an ordinary Core
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
        RuntimeAuthorityReference("parent-docker"),
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

`runtime_authority` selects the enclosing runtime. `runtime_access` declares the
CPK instance's desired process access and must reference that same authority.
The composer carries it through `ProductInstanceConfiguration` into the compiled
CPK node. PostgreSQL, Secrets, and connector instances keep empty declarations;
reusable product contracts do not acquire permission. Graph encoding, saved
plans, and public client requests preserve the declaration.

Workspace registration independently admits the exact delivery before execution.
Registration without a node declaration supplies no process access. Only local
Docker socket delivery is supported by this composer. Bootstrap projects socket
and group delivery from the declared graph into its validated acquisition plan.
Matching reference names in different workspaces do not share admission.

This changes the desired graph and plan identity. Review a fresh plan for a fresh
installation; old saved plans, uncertain runs, and retained resources are not
rewritten or adopted. Package tests and source adoption do not prove a published
image or live installation has adopted this boundary.

The root `bootstrap.sh` driver, protected initial material, authenticated child
setup through public APIs, approval/execution, automatic ingress runtime proof,
and durable grandparent tracking after restart remain CPK #1778/#1779 follow-ons.
Canonical CPK and Secrets image coordinates now consume the verified publications
recorded in [Servers #158](https://github.com/OpenJ92/control-plane-kit-servers/issues/158).
The CPK image was built from Servers `4468cd0`; the Secrets image uses that same
packaging source and Secrets `68d0da6`. Selecting these descriptors does not repin
a retained installation or establish installed-cluster acceptance.

Source-built CPK images declare numeric user `10001`, retaining the existing
`cpk` account, group and home. Protected provider-client files use that inspected
image UID with mode `0400` and a read-only mount. Older images declaring the named
user `cpk` are unsupported by numeric protected-file delivery. The newly selected
published CPK image declares numeric `10001`; old image digests remain unchanged.

## Website in the installation

Servers #299 adds `website=None` to preserve existing callers. For the complete
#225 installation, supply a `DockerCpkWebsite` with a separately reviewed immutable
image and explicit exposure intent. Building the value does not select, publish
or qualify that image.

```python
from dataclasses import replace
from control_plane_kit_servers_cpk_server import DockerCpkWebsite

def include_website(desired, reviewed_website_image):
    website = DockerCpkWebsite(
        image=reviewed_website_image,
        ingress=NamedPublicIngress(
            ingress_id="child-a-website-public",
            authority_ref=IngressAuthorityReference("parent-cloudflare"),
            target=PublicIngressTarget(desired.website_node_id, "http"),
            connector_node_id="child-a-website-connector",
            hostname="web.child-a.example.test",
        ),
        connector_product=desired.connector_product,
    )
    return compose_docker_cpk_installation(replace(desired, website=website))
```

This extends the example above to six nodes in the same workspace, runtime and
network: CPK, PostgreSQL, Secrets, website and two connectors. Both connector
documents must have canonical bytes, the ordinary revision-1 cloudflared identity
and an empty runtime contract. Their node IDs must differ from each other and
all four product node IDs. Ingress IDs and hostnames must differ; each supplied
ingress lifecycle is preserved. The website node is always
`<installation_id>-website`, with provider `http`, port 8080 and `PORT=8080`.
Its only upstream is `https://` plus this installation's API hostname.

The other supported profile uses `ExternalInstallationIngress` for both API and
website, with both connector documents absent. It yields four nodes and no
graph-owned ingress allocations. Both endpoints must satisfy the existing
[frontend canonical HTTPS origin rule](frontend-deployment.md). The website
upstream is exactly the API endpoint; the website endpoint remains explicit
exposure intent, without claiming provider allocation. Root acquisition
accepts this option through the [complete local root profile](complete-root.md),
which requires actual public receiving configurations and two explicit loopback
bindings. Production image qualification and external browser acceptance remain
separate.

Mixed Named/external profiles are refused. Origins must have distinct hostnames,
even when their ports differ or one hostname has a terminal DNS root dot.
Accepted origin bytes are preserved; no DNS lookup or normalization occurs.
New website/profile errors are fixed and omit rejected values. Existing backend
and API validation retains its original errors and runs first. Website-free
installations retain their existing external-endpoint and connector admission.

The website reuses `frontend_product`; its image and API upstream determine its
product identity. Existing backend nodes, store edges, configuration, credential
references and runtime access remain unchanged. The website has no secret
delivery, provider/admin credential, Docker access, retained data, protected
control surface or verification check. Empty verification means unverified
readiness. Public browser operation, image compatibility, restart/history and
survival after managed Hello teardown still require #225/Web #6 evidence.
This composition performs no acquisition, durable mutation or cleanup.

## Explicit managed-health configuration

Managed health defaults to absent. To include it in a new reviewed installation,
construct a public artifact from the closed process format described in
[managed-health startup](../../../docs/managed-health-startup.md):

```python
from dataclasses import replace
from control_plane_kit_servers_cpk_server.managed_health_configuration import (
    managed_health_configuration_artifact,
)

# reviewed_bytes contains the explicit scopes and canonical product documents.
artifact = managed_health_configuration_artifact(reviewed_bytes)
desired = replace(desired, managed_health_configuration=artifact)
topology = compose_docker_cpk_installation(desired)
```

The composer adds `cpk-managed-health` at
`/etc/cpk/cpk-server/managed-health.json`, JSON mode `0444`, and the CPK process
inputs `CPK_MANAGED_HEALTH=docker-unix-v1` and
`CPK_MANAGED_HEALTH_CONFIGURATION_FILE=/etc/cpk/cpk-server/managed-health.json`.
It uses ordinary graph configuration delivery. The selected image coordinates,
other instances, installation-composed credential references and explicit runtime
access declaration are preserved. The CPK variant identity changes with the
artifact content. No image is selected or published by this helper.

The original selected CPK contract must leave those environment names and the
artifact ID/path unused, including configuration requirements. Even an identical
existing declaration is refused. Existing base-product restrictions on secret
deliveries and retained mounts still apply before composition. Unrelated public
configuration is preserved.

The process Unix socket must match the installation's delivered
`/var/run/docker.sock`. Managed scope references remain exactly as supplied;
they may describe future managed workspaces and are not inferred from the
installation's placement. Declaring them does not admit their authority.

Outer UTF-8 bytes, including JSON whitespace, are preserved. Core computes the
content digest and checks descriptor digests on admission. A valid distinct
`source_digest` is retained as caller-asserted metadata, not proof of origin.
Configuration is public: never put credentials into this artifact.

The artifact limit is 262,144 bytes. The complete composed product independently
has Core's 262,144-byte document limit, so a maximum-sized artifact will not fit
inside that envelope. The standalone process reader permits 1,048,576 bytes;
that larger reader bound does not enlarge topology delivery. Root input and
plan envelopes each have their own 1,048,576-byte bound, including repeated and
escaped content. A new artifact requires a freshly reviewed plan and process
restart. Source tests do not establish that a retained or published image has
adopted this optional mode.

The owning `./test.sh` exercises three product-owned composition tests using real
descriptors, graph compilation and the graph codec, followed by the repository's
existing source/live validation phases. No new test runner or provider fixture is
introduced.

## Explicit control authentication

Existing installations default to `SingleOperatorControlAuth()`. Select
`MultiPrincipalControlAuth(SecretReference("secret://example/cluster/principals"))`
through the installation's `control_auth` field to use the server's existing
private principal document format.

The document reference must differ from `control_credential`, the separate
operator bearer for bootstrap/setup. Root material admission requires both.
Multi mode uses existing secret environment delivery and omits both legacy
single-credential and single-workspace-grants environment inputs.

In multi mode `workspace_grants` declares setup requirements, not effective
authority. The private document and existing server verifier determine each
principal's kinds and scopes. A client role label cannot elevate a credential.

The shared closed codec accepts
`{"kind":"multi-principal","principals_document":"secret://example/cluster/principals"}`
or `{"kind":"single-operator"}`; omitted root input preserves the default.
Graphs contain references, never resolved credential documents. Resolved secret
environment remains visible to trusted Docker/host administrators. Each cluster
retains its own CPK, PostgreSQL, Secrets instance and credential documents.
# Selecting managed PostgreSQL

Supply an explicit `postgres-server` descriptor whose immutable image is the
qualified managed PostgreSQL artifact and whose contract is authored with
`postgres_source_runtime_contract(postgres_control_configuration_artifact(configuration))`.
Do not replace the image on the historical native descriptor: it describes a
different process contract.

The public configuration names this installation's workspace, `<installation>-docker`
runtime, `<installation>-postgres` node, `management` socket and a distinct
receiver ID. It requires the product's surface/health verifier families and may
reuse existing public verifier keys. The original two-role commissioning receipt
does not establish this third receiver; supply and review it separately. Never
put private signing keys in configuration.

Composition preserves PostgreSQL 5432, private management 8000, the read-only
control artifact, retained data and the owner-only password file. The installation
password reference serves both PostgreSQL and the CPK client; DB/user remain
`cpk`. Startup requires authenticated `SELECT 1`, independently of signed health.
Managed shared password input must be nonempty valid UTF-8 without NUL or trailing
LF. Bootstrap rejects ambiguous trailing LF before acquisition rather than giving
the file reader and CPK environment different effective credentials. Native-root
input semantics remain unchanged. The synchronous Linux driver bounds attached
SQL observation with a scoped signal deadline; expiration holds the pending
acquisition without retry and does not claim remote-command cancellation.
The external driver includes the managed product authoring code; the accepted
CPK/Secrets runtime images can remain selected. Fresh acquisition still refuses
existing resources: this is not a native-volume migration, adoption or repair.
