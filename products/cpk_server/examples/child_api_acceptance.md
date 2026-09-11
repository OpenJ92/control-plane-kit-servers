# Public child installation acceptance

Governing issue: [Servers #163](https://github.com/OpenJ92/control-plane-kit-servers/issues/163).
The acceptance journey is grandparent → new parent → Hello/router application
with a delegated gateway. Component tests and the ordinary root bootstrap smoke
do not prove this joined journey. No new live acceptance is claimed by this source.

`public_child_api.py` supplies the composition and evidence helpers;
`tests/live_child_api.py` uses the maintained `TopologyClient` and public HTTP
contracts. Neither has a Docker socket, SQL connection or provider client.
The owning `test.sh`, `live_child_fixture.py` and `live_child_resources.py`
supply the separately released initial custody, exact resource observations,
restart and retained-resource disposition. Do not run an alternate harness.

## Source and image coordinates

The controller source consumes Core/Operations
`087a89253b14b3bb438af9042ea779976886a79e` and Interpreter
`ba9f7a2e4cdb8b32e54e81cd7e37658562776221` (I3). The three CPK catalogue
variants share the published D3 image
`sha256:1ba7174ee22461566750a516dac173fdd718ed9b059660f30c3ad3f9db79d0f4`,
produced from Servers S3 `3ffc4952015b7eb2c379978c52cab56eaee5853a`.
The publication tag is `diagnostics-170-3ffc495`; digest identity governs execution.
This example changes controller composition, not those image bytes.
The child controller's read-only source mount supplies the Hello renderer used
to calculate the expected body hash. The harness adds that source package to
the controller's import path; it does not install Hello in the CPK graph image.

Only the selected new parent's CPK product document adds the existing
`CPK_GATEWAY_PROBE_SIGNER=ed25519` process setting, retaining provider-backed
material resolution and the same image/provenance. Catalogue defaults are
unchanged. The composed CPK node alone receives explicit Docker runtime access;
each workspace independently admits its own runtime authority and delivery.
Enabling an interpreter does not grant runtime authority.

Hello, HTTP active router, CPK local gateway and cloudflared connector use their
exact canonical product documents in the reviewed source. Preflight requires
all installation and application image digests already cached. There is no
implicit image pull, new image build/publication or fresh-pull proof in the
child acceptance branch.

## Endpoints and consumers

The retained grandparent bootstrap endpoint is
`https://cpk-bootstrap-grandparent.openj92.dev`. The controller uses that CPK API
to deploy the new parent. The run's root connector uses a protected copy of the
retained tunnel credential and its existing origin binding. The original
tunnel, DNS record and protected credential remain outside fixture ownership.

Two fresh named ingresses have distinct consumers:

- The new parent's CPK control ingress is used by the controller for authenticated
  workspace setup, application deployment, history reads and gateway-probe commands.
- The application's `NamedPublicIngress` targets `gateway.control`. The new
  parent's runtime uses that HTTPS endpoint to dispatch a signed delegated probe.
  Its exact hostname follows `<fresh-run-prefix>-gateway.openj92.dev` and is
  bound in the concrete release. It has its own connector and exact-host authority.

The application graph is Hello `internal` → router `active`, then router
`internal` → gateway `target-http`. Those target connections stay private.
There is no public Hello/router/browser ingress. Calling the parent's CPK API
and the parent probing its application are separate HTTP legs. The existing
named-ingress value binds one hostname to one target socket; this example does
not add hostname fanout, proxy routes or private-network repair.

## Credentials and initial custody

The fixture creates separate operator, approver and worker credentials in each
workspace. The new parent also has a distinct probe principal. Existing
`cpk.client-profile.v1` profiles supply credential-file references; the probe
profile maps its required three role slots to the same low-power probe credential
and invokes only its operator transport role. This does not grant approval or
execution powers to that credential.

The setup operator has existing workspace, provider, runtime, plan and ingress
admission scopes, plus delegation-key register/read/activate. It does not have
`gateway-probe:use`. The probe principal has only workspace-read,
`gateway-probe:use`, `delegation-key:use` and `secret-provider:use` for its exact
workspace. Approvers retain approval scopes; workers have execution and provider
use. Requests never supply `actor_scopes` as authority.

Initial custody occurs in two finite phases:

1. Before parent deployment, the root's Secrets custody receives the parent's
   control credential, principal document, PostgreSQL password, custody root
   key, provider credential document/client credential and approved Cloudflare
   API token. Existing public setup admits their references and intents.
2. After parent deployment and authenticated initialization, exact installation
   observations bind its CPK container namespace. Before any application plan,
   a socket-free fixture process in that namespace writes only the dedicated
   fixture Ed25519 private key and the approved Cloudflare API token to the
   parent's local Secrets service. This is initial application custody, not
   post-failure repair or production credential generation.

The second phase uses an initializer credential distinct from the delivered
runtime credential. Its provider grant permits writes for only
`gateway.probe-signing-key` and `cloudflare.api-token` in the exact workspace.
The delivered runtime credential can resolve admitted application intents and
write generated `cloudflare.tunnel-token` values; existing metadata/revoke
provider grants are workspace scoped. The current provider vocabulary does not
claim a finer reference-level restriction for metadata/revoke.

Every custody request persists pending intent before dispatch. Returned version
coordinates are persisted before checking returned workspace, encoded secret
reference, intent, active status and positive version number. A mismatch leaves
pending evidence and stops; exclusive phase directories prevent blind retries.
The initializer credential is not a CPK principal or the runtime client token.
Values remain in protected fixture custody and never enter public plans/history.

The parent then registers its exact gateway ingress authority using the actual
provider registration returned by initialization, registers and activates the
public signing key with its private-key reference, and reads both admissions
back through existing public APIs. No secret is returned by those admissions.

## One-run release

The private release binds the reviewed clean source commit, fresh installation
and workspace identities, exact account/zone and hostnames, retained bootstrap
connection, restart, and retained-volume disposition. Historical run names and
receipts do not authorize adoption. A conflicting resource stops preflight.

```json
{
  "schema": "cpk.child-acceptance-release.v1",
  "source_head": "REVIEWED_COMMIT_REQUIRED",
  "parent_installation_id": "FRESH_GRANDPARENT_ID",
  "parent_workspace_id": "FRESH_GRANDPARENT_WORKSPACE",
  "child_installation_id": "FRESH_PARENT_ID",
  "child_workspace_id": "FRESH_PARENT_WORKSPACE",
  "loopback_port": 18089,
  "parent_endpoint": "https://cpk-bootstrap-grandparent.openj92.dev",
  "parent_ingress_connection": {
    "tunnel_id": "ACTUAL_RETAINED_TUNNEL_UUID",
    "dns_record_id": "ACTUAL_RETAINED_DNS_ID",
    "token_reference": "secret://bootstrap/retained-ingress/token",
    "token_sha256": "APPROVED_PROTECTED_TOKEN_SHA256",
    "configuration_sha256": "APPROVED_EXACT_CONFIGURATION_SHA256"
  },
  "account_id": "REQUIRED",
  "zone_id": "REQUIRED",
  "zone_name": "openj92.dev",
  "hostname": "FRESH_PARENT_HOSTNAME",
  "gateway_hostname": "FRESH_RUN_PREFIX-gateway.openj92.dev",
  "retained_disposition": "REQUIRES_EXPLICIT_CHOICE"
}
```

The historical harness field names `parent_*` identify the bootstrap grandparent;
`child_*` identify the new parent installation/workspace. Application node IDs
are derived from that new parent's installation ID.

After concrete source/plan review and effect authorization, unchanged `./test.sh`
consumes `CPK_CHILD_ACCEPTANCE_RELEASE`, `CPK_CHILD_ACCEPTANCE_DIGEST`,
`CPK_CHILD_ACCEPTANCE_RUN`, `CPK_CHILD_CLOUDFLARE_TOKEN_FILE` and
`CPK_PARENT_TUNNEL_TOKEN_FILE`. The digest binds exact input bytes; it does not
itself grant permission. Ordinary tests and hosted CI leave all five unset.
Credential values and locations do not belong in public issues or handoffs.

Before live execution, inspect the exact retained tunnel/DNS and two-rule origin
configuration, absence of active connections, and exclusive operator use. The
stable tunnel-derived connector name prevents a second local connector; it is
not a global lock. Root bootstrap does not create, adopt or remove that ingress.

## Ordered witness and evidence

1. Bootstrap the disposable grandparent through `bootstrap.sh`, using its actual
   receipt. Seed initial root custody and create protected client profiles.
   Require cached images and absence of both fresh DNS hostnames.
2. Through the grandparent's public API, deploy the composed parent installation
   with exact plan operation/target multiset review. Bind client journal input
   digest, graph/projection/plan/run identities and authenticated root identity.
3. Initialize the parent through its HTTPS API and prove wrong-credential denial.
   Connection/TLS failure is not denial evidence. Observe its exact four
   containers, network, owned volumes and named ingress before local custody.
4. Complete initial application custody in that exact namespace. Publicly admit
   the gateway authority and signing key, activate the key, and read it back.
5. The parent plans and deploys Hello/router/gateway/connector. A router root-path
   `HttpCheck` preserves existing health checks and verifies the exact rendered
   Hello body SHA256. Read evidence must match current graph, deployment run,
   node, socket, check, path and fresh successful observation.
6. Observe all four application containers, network, owned volumes and gateway
   ingress separately from the installation. Restart only the receipt-owned
   grandparent CPK process; preserve its PostgreSQL, Secrets and descendants.
7. Require unchanged grandparent session/plan/run/event history and current
   projection, and the parent's current application graph and deployment run.
   Then issue one new parent-authorized gateway probe over
   `named-public-ingress`. Bind request, actor, graph, gateway/runtime, target,
   key, grant time interval and exact returned attempt. Reject replayed results.
   Read back that same durable attempt. The fresh probe proves HTTP 200 and a
   positive bounded response size. It does **not** prove a fresh body hash;
   deployment body-hash evidence remains a separate fact.
8. Save/select/read an EMPTY application revision, prepare that saved revision,
   inspect and approve its exact destructive plan, and apply through the parent
   API. Verify exact application compute and gateway DNS/tunnel absence before
   allowing the parent's own teardown.
9. Save/select/read EMPTY in the grandparent workspace and apply its exact
   approved destructive plan to remove the parent installation. Reconcile all
   recorded compute and ingress absences. No direct Docker child deletion counts.
10. Apply the explicitly selected `retain` or `delete-owned-fixture-volumes`
    disposition to exact recorded owned volumes. Deletion is non-force, with
    pending intent and absence verification. Complete root receipt cleanup only
    after every child phase is complete. Original retained ingress/token survive.

Empty graph convergence does not prove deletion of PostgreSQL/Secrets data or
protected file volumes. Presence observations prove volume objects, not their
content integrity. A failed or uncertain phase preserves the root, pending
journal and known returned IDs. There is no automatic repair, rekey, redispatch,
broad prune or unbounded provider inventory. Logs supplement structured history;
all witness failures use bounded fixed messages without raw provider responses.

Composition, credential separation, custody identity/refusal and evidence laws
are protected by `test_child_api_example.py` and `test_child_gateway_example.py`.
Their green results must be obtained at the reviewed source checkpoint through
the ordinary `./test.sh` gate. The later live release still needs exact source,
image, endpoint, custody, restart and cleanup evidence; unit tests cannot supply it.
