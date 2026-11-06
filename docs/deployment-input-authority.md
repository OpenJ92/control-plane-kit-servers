# Configured authority for deployment inputs

The #341 source factory now also accepts typed trusted
`WorkspaceAuthorityConfiguration`: existing administration and managed-runtime
capability policies for one installation. In that dynamic mode, the factory
supplies the existing durable principal authorizer for generation/provision and
the current workspace resolver for HTTP/MCP. Supplying a separate static
principal authorizer at the same time is rejected. Startup requires an existing
matching installation receipt before provider clients; it does not initialize
the receipt or seed grants. Ordinary empty-schema creation can precede refusal.

The combined #341 source is accepted at
`e08694a35f3e343a664608dd3e0bcf06283d6300`, including trusted file/environment
inputs, public-client queries and semantic invocation forwarding. Independent
source review and [owning run 40645842537](https://github.com/OpenJ92/control-plane-kit-servers/actions/runs/40645842537)
passed 1,109 package tests plus 26 support tests, the real process/verifier/public
PostgreSQL fixture and final Docker residue audit. See the
[evidence receipt and limits](https://github.com/OpenJ92/control-plane-kit-servers/issues/341#issuecomment-6462868979).

Dynamic process inputs are described in
[workspace authority startup](implementation/workspace-authority-startup.md).
Supported fresh dynamic-bootstrap delivery, explicit owner initialization and
public enrollment remain a separate prerequisite; the existing installation
artifact helper stays v1-only. G/#342 still owns composed public lifecycle,
ingress denial and retained-upgrade acceptance. This is not live enablement.

## Static development policy

The CPK process composes provider-backed delegation-key generation and protected
HTTP material provision when the corresponding provider port and an explicit
current-principal authorizer are present. In static mode, main derives
that authorizer from the existing static-development startup configuration:
`CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON`, or the single-operator credential and
`CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON`. No new credential format is added.

The verifier authenticates requests. A separate credential-free policy directory
decides their current permitted scopes. Identity includes issuer, subject and kind;
grants are workspace-specific. Equal configured policies for one identity collapse.
Conflicting policies deny that identity entirely, even when attached to different
credentials or disjoint workspaces. A decision can only reduce the original
authenticated request's scopes. Operations still checks the scopes required for
each operation, current provider registration and durable generation state.

This is restart-configured development policy. Changes take effect in a replacement
process. It does not provide hot reload, in-flight revocation, token/session
revocation or a persistent authorization service. The authorizer stores no bearer
credentials. Existing verifier credential custody remains unchanged.

In static mode, programmatic callers of `create_app` must explicitly pass `principal_authorizer`
to enable generation or provision; an injected verifier, including a static verifier, is not
treated as a policy directory. In dynamic mode, the factory supplies the durable
authorizer from validated workspace authority and rejects an additional static
authorizer. The shared Operations factory also requires the
generator port for generation, and the existing custodian for provision. Each
service remains unavailable (501 for an otherwise authorized request) when either
of its dependencies is absent. Generation does not implicitly enable provision.
Provider configuration resolves admitted references using the existing public
client; adapter construction does not read provider credential files or call it.

Generation uses provider custody and returns safe references/public metadata.
Operations owns generation/registration permissions, attempts, receipts, admission,
uncertainty and structured history. Provision uses the accepted Operations owner
with the same UoW/clock and existing provider custodian. It reserves an attempt,
performs custody IO outside that transaction, then records the outcome/admission
through its existing transaction boundary. Duplicate requests return conflict with
safe status navigation; they do not redispatch custody. Pending or uncertain
outcomes remain owner state, not permission to retry, adopt or claim success.
No new concurrent-write, rollback or compensation algorithm is introduced.
See [confidential transport](confidential-transport.md) for byte limits, ordering
and the protected stdin example. The selected source is covered by the #341
owning gate above; live enablement remains separate.

## Principal and provider grants

| Operation | Required CPK scopes | Provider capability |
| --- | --- | --- |
| Generate a signing key | delegation-key:generate and delegation-key:register | secret.generate-delegation-key for the exact purpose-derived intent |
| Provision confidential material | secret-material:provision and secret-provider:register | secret.write for the requested supported intent |
| Activate an admitted key | delegation-key:activate | None |
| Read provision status | instance:workspace:read and secret-provider:read | None |
| Read authoring context | instance:workspace:read and delegation-key:read | None |
| Prepare deployment | instance:workspace:edit and plan:request, plus applicable admitted authority/use policy | Existing owner-selected metadata reads where needed |
| Approve / execute | Distinct approval scopes / worker or service execution authority | Only the subsequently authorized effect |

Provider registration bounds workspace, reference prefixes and allowed intents.
Provider bootstrap credentials independently grant capabilities; CPK registration
does not confer a missing provider grant. Provider metadata and revoke grants are
workspace-scoped, without per-reference filtering. Do not model a reference prefix
as narrowing those provider grants. Read-only viewers receive neither provision
nor execution authority. Operator approval is not worker execution.

## Preparation and downstream inputs

The maintained witness starts without managed instances, authenticates real CPK
commands, generates provider-owned keys, provisions synthetic external material,
activates keys and reads real public verifier/context values. Existing product
owners turn those public values into Hello/gateway/connector artifacts. Gateway
and connector declarations remain canonical and instance-free; their selected
instance artifacts hold trust. Preparation records plan/session/history and asks
for approval without advancing current graph or executing activities. The ingress
authority consumes an admitted reference; this is not invented version pinning.

Selected source cohort: Core `4cc1716bef4d7548ddb4cd343e53fa06bb447104`,
Operations `b08d87668b7208042ecd8dda68770ccb9cdf41c1`,
SDK `464df26c568971362eb3a08abaf9dfc227a4ddbb`,
Secrets `067678fbaa297d3206ff13d018c69bc14387e46c`,
Interpreters `bd08b931ae9241878ce4f4b7072f95ccebfa3536`.
Downstream #225 must additionally select reviewed Servers/image identities,
installation API/site bindings, protected credential custody, complete real graph,
separate application and management ingress, exact approval/execution and owned
cleanup plans. This source witness does not provide those live inputs or release
their effects. Preserve the installation, history and original tunnel/DNS/token.

Source validation does not qualify new images or establish live #225 behavior.
Historical product images, retained tunnel/DNS/token and commissioning custody
remain separate from this source composition.
