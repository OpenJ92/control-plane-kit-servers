# Configured authority for deployment inputs

The CPK process can compose provider-backed delegation-key generation when it has
both a provider registry and an explicit current-principal authorizer. Main derives
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
to enable generation; an injected verifier, including a static verifier, is not
treated as a policy directory. The shared Operations factory also requires the
generator port. With either dependency absent the generation service is unavailable.
Provider configuration resolves admitted references using the existing public
client; adapter construction does not read provider credential files or call it.

Generation uses provider custody and returns safe references/public metadata.
Operations owns generation/registration permissions, attempts, receipts, admission,
uncertainty and structured history. No implicit retry or private store seeding is
introduced. Confidential secret-material provision remains unavailable in #315
and #316. #317 must explicitly compose and test authority, custody, bounded HTTP,
confidential representations and early HTTP-only MCP refusal before enabling it.

Source validation does not qualify new images or establish live #225 behavior.
Historical product images, retained tunnel/DNS/token and commissioning custody
remain separate from this source composition.
