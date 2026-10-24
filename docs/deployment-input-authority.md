# Configured authority for deployment inputs

The CPK process composes provider-backed delegation-key generation and protected
HTTP material provision when the corresponding provider port and an explicit
current-principal authorizer are present. Main derives
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

Programmatic callers of `create_app` must explicitly pass `principal_authorizer`
to enable generation or provision; an injected verifier, including a static verifier, is not
treated as a policy directory. The shared Operations factory also requires the
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
and the protected stdin example. This source implementation is pending the #317
normal green gate and integrated review; it is not a live enablement claim.

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

Selected source cohort: Core/Operations `879efb9576ac0580a6236d0a7372c036537b4dfe`,
SDK `43838fd0f4391428cfffa87f8c4dbd5cc6d5eab1`,
Secrets `78a2ed7c8abee6da31f8661993ed4c5426edd7ee`,
Interpreters `6faf6698e47381476fb2f09058894eab16f0c768`.
Downstream #225 must additionally select reviewed Servers/image identities,
installation API/site bindings, protected credential custody, complete real graph,
separate application and management ingress, exact approval/execution and owned
cleanup plans. This source witness does not provide those live inputs or release
their effects. Preserve the installation, history and original tunnel/DNS/token.

Source validation does not qualify new images or establish live #225 behavior.
Historical product images, retained tunnel/DNS/token and commissioning custody
remain separate from this source composition.
