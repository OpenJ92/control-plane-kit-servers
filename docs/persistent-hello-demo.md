# Persistent Public Hello Demo

Run a private CPK control plane and a public Hello application. After bootstrap,
all application topology changes enter authenticated **MCP over HTTP** at
cpk-server. The client constructs desired graph values; CPK plans, authorizes,
executes and records them. Docker is not a parallel application control path.

This is a local, user-authorized demonstration, not a production installer or
an autonomous recovery service. It uses static development principals and a
Docker socket available only to the control-plane server. Keep control access
on loopback; expose only application traffic through your tunnel.

## Prerequisites

- Docker with capacity for CPK, Postgres, your custody service, a router,
  cloudflared and the requested Hello nodes. Host port 18080 must be free.
- Access to the source dependencies and exact product image digests in
  `products/*/product.cpk.json`. Some GHCR packages are private. Use your own
  registry login before bootstrap; never give registry credentials to Hello.
- Run the repository's ordinary `./test.sh` successfully. It builds the local
  controller and cpk-server images and validates their composition. Stop on
  missing prerequisites or apparatus failure; do not replace the suite with a
  host Python environment. This command runs tests and owned smoke resources,
  not the persistent application.
- Cache the exact Hello, active-router and cloudflared product digests and
  a compatible Postgres image, such as `postgres:16-alpine`. Acquiring images is
  an explicit setup step. The retained launcher does not accept registry config
  and does not silently substitute another image. Building cpk-server from
  source is supported; rebuilding a workload does **not** reproduce its published
  digest or authorize changing its descriptor. If you cannot access the pinned
  workload images, resolve publication/access before proceeding.
- Your own hostname and already-configured Cloudflare tunnel. Configure its
  public-hostname origin as `http://application-router:8000`, with a fallback
  404, and its DNS mapping to your tunnel. The connector needs normal DNS and
  outbound Cloudflare connectivity. This guide does not create tunnels or edit
  DNS. Owning a hostname does not by itself configure a tunnel.
- An existing reachable [CPK secrets provider](https://github.com/OpenJ92/control-plane-kit-secrets)
  holding that tunnel token. Supply an opaque reference and a separate,
  least-privilege server credential allowing resolve only for your application
  workspace and `cloudflare.tunnel-token` intent. Store the credential in an
  owner-only file. A Cloudflare account API token is **not** a tunnel token.
  Custody bootstrap, encrypted storage/master-key backup and token provisioning
  are separate prerequisites; no maintainer's private setup file is required or
  supplied here.

Do not run this guide against an existing installation you do not own. Replace
all example configuration below with your own approved values. Use a durable
directory, not a temporary checkout/evidence root.

## Bootstrap Once

From this repository root, after the prerequisite package gate and image
acquisition, record immutable local identities:

```sh
export CPK_SERVER_IMAGE="$(docker image inspect --format '{{.Id}}' localhost/control-plane-kit-servers/cpk-server:local)"
export CPK_SERVERS_TEST_IMAGE="$(docker image inspect --format '{{.Id}}' control-plane-kit-servers-test:local)"
export CPK_DEMO_POSTGRES_IMAGE="$(docker image inspect --format '{{.Id}}' postgres:16-alpine)"
export CPK_DEMO_INSTALLATION_NAME=my-cpk-demo
export CPK_DEMO_INSTALLATION_DIR="$HOME/cpk-installations/my-cpk-demo"
export CPK_PUBLIC_CONVERGENCE_EVIDENCE_PARENT="$HOME/cpk-evidence/my-cpk-demo"
mkdir -p "$HOME/cpk-installations" "$CPK_PUBLIC_CONVERGENCE_EVIDENCE_PARENT"
chmod 700 "$HOME/cpk-installations" "$CPK_PUBLIC_CONVERGENCE_EVIDENCE_PARENT"

export CPK_DEMO_APPLICATION_WORKSPACE=my-hello-demo
export CPK_DEMO_WORKSPACES=my-hello-demo,my-sandbox
export CPK_DEMO_PROVIDER_URL=https://your-custody-endpoint.example
export CPK_DEMO_PROVIDER_CREDENTIAL_FILE="$HOME/.config/cpk-demo/provider-client-token"
export CPK_DEMO_TOKEN_REFERENCE=secret://persistent-demo-secrets/application/tunnel-token
export CPK_DEMO_BOOTSTRAP_APPROVED=1
CPK_PUBLIC_CONVERGENCE_MODE=bootstrap \
  sh scripts/cpk_server_public_graph_convergence_smoke.sh
unset CPK_DEMO_BOOTSTRAP_APPROVED
```

The installation directory itself must not already exist. Bootstrap creates
the private CPK/Postgres network, durable Postgres volume, local control server,
and distinct operator/approver/worker credentials. It records exact resource and
image identities and copies only the narrow custody credential for the server.
It does not create the custody service, tunnel, DNS record or application graph.
The bootstrap marker is not proof of application connectivity.

Keep generated files private; do not print, commit or send `controller.env`,
`server.env`, `postgres.env` or the copied credential. The launcher loads them
without requiring you to paste tokens into commands. Preserve the recorded image
IDs for later attach; a newer local tag does not authorize replacing this
installation. A failed bootstrap stops: do not rerun into the partial directory
or remove resources without an explicit ownership/disposition check.

## Create And Edit The Application

The committed retained client has a deliberately small CLI: node count,
capacity, and active-node index. It uses stable `hello-1`, `hello-2`, ...
identities, `service-N` greetings and a fixed color sequence. Capacity counts
Hello nodes, not the router/connector/control-plane containers.

Each attach is one authorized desired-graph submission using separate roles.
It prepares and inspects the public plan, approves within the supplied scope,
executes, advances current only on success, and retains a bounded report. It is
**not** an interactive plan-only UI; use the public commands below if you want
to inspect a specific plan before deciding approval.

```sh
export CPK_PUBLIC_CONVERGENCE_APPROVED=1
export CPK_PUBLIC_CONVERGENCE_CAPACITY=4

# First application submission only: one Hello, router, connector.
CPK_PUBLIC_CONVERGENCE_MODE=attach CPK_DEMO_CREATE_WORKSPACE=1 \
  CPK_PUBLIC_CONVERGENCE_NODES=1 CPK_DEMO_ACTIVE_NODE=1 \
  sh scripts/cpk_server_public_graph_convergence_smoke.sh

# Add two Hello nodes, preserving the current selected node.
CPK_PUBLIC_CONVERGENCE_MODE=attach \
  CPK_PUBLIC_CONVERGENCE_NODES=3 CPK_DEMO_ACTIVE_NODE=1 \
  sh scripts/cpk_server_public_graph_convergence_smoke.sh

# Select the existing second node; no additions or removals.
CPK_PUBLIC_CONVERGENCE_MODE=attach \
  CPK_PUBLIC_CONVERGENCE_NODES=3 CPK_DEMO_ACTIVE_NODE=2 \
  sh scripts/cpk_server_public_graph_convergence_smoke.sh
```

Run each command only after the prior one is green. Keep `CPK_DEMO_CREATE_WORKSPACE`
unset after the first submission. Visit the exact root `https://YOUR-HOSTNAME/`;
the current Hello product returns an HTML greeting with its configured accent.
Older immutable Hello images still return plaintext. Its exact-root
handler does not accept cache-busting query strings. A graph count/selection
repeated after successful completion can produce `no-changes`, with no run;
that is not authority to replay an uncertain failed invocation.

To remove the second/third nodes safely, first switch to node 1 while retaining
all three and verify its public response. Then, as a **separate authorized
destructive submission**, set nodes=1:

```sh
CPK_PUBLIC_CONVERGENCE_MODE=attach \
  CPK_PUBLIC_CONVERGENCE_NODES=3 CPK_DEMO_ACTIVE_NODE=1 \
  sh scripts/cpk_server_public_graph_convergence_smoke.sh
# Stop unless this completed and the expected public root response is verified.
CPK_PUBLIC_CONVERGENCE_MODE=attach CPK_PUBLIC_CONVERGENCE_DESTRUCTIVE_APPROVED=1 \
  CPK_PUBLIC_CONVERGENCE_NODES=1 CPK_DEMO_ACTIVE_NODE=1 \
  sh scripts/cpk_server_public_graph_convergence_smoke.sh
```

Do not assume a combined rewire/delete plan waits for router verification before
stopping the previously selected node: inspect actual dependencies. The live
example used two public transitions for that reason, not direct container removal.

## Public Plan And Approval Control

For custom names/messages or individually reviewed plans, construct the desired
graph using Core `ProductDescriptorCodec`, `ProductInstanceConfiguration`,
`instantiate_product`, `DeploymentTopology`, `DockerRuntime`, `SocketConnection`
and `DEFAULT_GRAPH_CODEC.encode(compile_topology(...))`. This is local value
construction, not provider execution. Use Hello `HELLO_MESSAGE` and `HELLO_COLOR`
configuration, stable identities, and a router expected-response check matching
the selected node. The retained demonstration used Jacob/blue, Mia/purple and
Elliot/green this way; the count-based CLI does not accept those custom names.

### Add HTML Alongside An Older Image

The current Hello descriptor pins
`ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:e3256ca3aeb52077527143c88d96b3b460080862459686e259d2464f41c1669b`
from source `cae307b34884e234ee8d96517012fe39c45e3dea`. It is **linux/amd64 only**;
confirm the runtime supports that platform before approving a plan. Registry
access remains private; importing a descriptor does not prove image access.

For example, construct the new product value from this repository's descriptor:

```python
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.products import (
    ProductDescriptorCodec, ProductInstanceConfiguration, instantiate_product,
)
from control_plane_kit_servers_hello_server.server import render_hello

product = ProductDescriptorCodec().decode_document(
    Path("products/hello_server/product.cpk.json").read_bytes()
).product
configuration = ProductInstanceConfiguration.from_contract(product.runtime_contract)
values = {"HELLO_MESSAGE": "Hello Jacob", "HELLO_COLOR": "blue"}
configuration = replace(configuration, public_environment=tuple(
    PublicStaticEnvironmentBinding(binding.name, values.get(binding.name, binding.value))
    for binding in configuration.public_environment
))
html_jacob = instantiate_product(product, "hello-jacob-html-blue", configuration)
expected_root_digest = sha256(render_hello("Hello Jacob", "blue")).hexdigest()
```

Run authoring code only in the repository's matching Docker client environment;
no host dependency setup is needed. The palette is exactly blue (default), purple,
green and red. Greeting text is escaped, and invalid colors stop startup. Graph
display metadata is not process configuration.

Keep the original authoring inputs/descriptors for all existing nodes. Append
`html_jacob` to those retained runtime children without changing their image,
environment, secret references or the current router edge. Do not regenerate
old nodes using the new catalogue: that is an image update, not preservation.
Do not replay the count-based attach example against a mixed old/new graph.

Submit that encoded full desired graph through `command.deployment.prepare`
below, using freshly read current/desired coordinates. Inspect its actual plan:
only the new node should be created; a runtime membership ensure must not change
the network or replace old containers. Approve/execute and verify the new node's
public health evidence. Only then submit a second desired graph changing the
router's `active` socket edge to `hello-jacob-html-blue` and its `root-response`
HttpCheck to `expected_root_digest`. Keep every node in both graphs. Verify the
successful public run/current graph and fresh exact HTTPS HTML response.

Using an existing node ID instead would update that node and can replace its
container with a brief outage; it needs that different inspected plan and
approval. Publishing, changing a descriptor, or adding an unselected node does
not itself switch the router. Old-node removal, DNS/tunnel changes and control
plane replacement are not part of this addition-and-switch procedure.

Use your authenticated client and the published CPK contract. For example, the
following JSON-RPC request reads current workspace coordinates:

```json
{
  "jsonrpc": "2.0", "id": "read-workspace", "method": "resources/read",
  "params": {"name": "read.workspace", "arguments": {"workspace_id": "my-hello-demo"}}
}
```

Send to `POST http://127.0.0.1:18080/mcp` with `Authorization: Bearer <operator
credential>`, `Content-Type: application/json`, `MCP-Protocol-Version: 2025-06-18`
and `Mcp-Method: resources/read`. Commands use JSON-RPC `tools/call` and
`Mcp-Method: tools/call`; `params.name` is the command ID. Keep credentials in
your client/private files, not shell history, screenshots or reports. HTTP and
MCP share the service contract; this guide's concrete transport is MCP over HTTP,
not a claim that each operation was independently run through both bindings.

The preparation command's `params` has this shape (replace placeholders with
actual prior public values and your encoded graph, not quoted placeholders):

```json
{
  "name": "command.deployment.prepare",
  "arguments": {
    "workspace_id": "my-hello-demo", "idempotency_key": "your-unique-intent-key",
    "title": "Select existing Jacob; retain other nodes",
    "desired_graph": "<encoded desired graph object>",
    "expected_current": "<current authored_graph_id / realized_projection_id object>",
    "expected_desired": "<desired pointer object or null>",
    "expected_desired_graph_revision": 1
  }
}
```

Derive every subsequent coordinate from public responses, not a copied demo UUID:

| Step | Public operation and handoff |
|---|---|
| Read | `read.workspace`, `read.current-graph`; current/desired pointers and revision. |
| Prepare | `command.deployment.prepare`; inspect `no-changes`, `review-blocked` or `approval-required`, plan/approval IDs. No external effects here. |
| Review | `read.plan-detail`, `read.approval-detail`; targets, dependencies, risk, destructive scope. |
| Decide | Separate approver calls `command.approval.decide` with approval/session IDs and `approved` or `rejected`. Removals require `plan:approve-destructive`. |
| Admit | `command.deployment.admit` with plan/session/approval IDs and readiness; returns execution request ID. |
| Claim/start | Worker calls `command.run.claim`, then `command.run.start` with returned run ID/claim generation. |
| Execute | Worker calls `command.deployment.execute` with run ID/generation, bounded `max_effects`; a new key for each intended next command. Continue only on `progressed`, finish only on `completed` plus succeeded run. |
| Advance | `command.graph.advance-current` with run/plan/generation, expected current graph/projection, desired graph/projection and revision from that plan. |
| Verify | `read.current-graph`, `read.plan-runs`, paged `read.run-events` and `read.observed-state`, plus fresh expected public application response. |

Every command carries its own idempotency key. A lost response, conflict,
in-flight/uncertain/blocked/failed/unsupported result is a stop, not a cue to
repeat effects or manually advance. Reject an unused pending approval publicly
before superseding its desired intent with exact current/desired revision
preconditions. Preserve that history. Public graph descriptors redact secret,
address and environment fields: retain your original authored intent and use
public coordinates/plans for correlation, not round-tripping redacted values.

## Retention And Teardown

Successful retained attach removes only its completed client container; it
leaves application nodes, CPK, Postgres/history, custody and tunnel running.
Failed clients/reports remain for diagnosis. Keep the printed evidence directory
private and consult durable public run/event truth; old observations can expire
and are not fresh reachability evidence.

The retained CLI requires at least one Hello and has no full-teardown command.
An empty application graph is a separate public prepare/review/destructive
approval/execute/advance operation; inspect all removals before approving. CPK
application teardown does not authorize deleting its own Postgres volume, custody
keys/data, DNS or tunnel. Installation disposal requires a separate backup and
exact ownership plan. Never use broad Docker prune or delete by name prefix.

Always set `CPK_PUBLIC_CONVERGENCE_MODE=bootstrap` or `attach` explicitly: omitted
mode selects the different disposable acceptance scenario, which includes
removals/teardown and is not an installation-resume mechanism.

Recorded public demonstrations and limitations: [servers #123](https://github.com/OpenJ92/control-plane-kit-servers/issues/123).
Source: [client](../scripts/cpk_server_public_graph_convergence.py) and
[launcher](../scripts/cpk_server_public_graph_convergence_smoke.sh).
