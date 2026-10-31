Source: [operations_application.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/operations_application.py).

## #341 typed dynamic composition

`WorkspaceAuthorityConfiguration` holds existing administration/capability
policies with one matching installation ID. The factory rejects competing static
principal authority and constructs the existing durable authorizer, current
workspace resolver and administrative command/read owners. The ordinary and
administrative routes share the same WorkspaceCommandService. Generation and
provision consume the durable authorizer when their existing ports are present.

One CurrentWorkspaceEffectPolicy feeds effect start, execution invocation,
ingress invocation, reconciliation and coordinator composition. Reconciliation
and coordinator share the same ExecutionInvocationService. The factory performs
no lookup or initialization during assembly. Static callers retain the prior
owner/default path. Existing owner type guards remain active; no policy or
invocation state machine is implemented here.

The factory default clock now emits canonical UTC ending in Z, matching the
existing server clock and accepted receipt contracts. Explicit caller clocks
are still forwarded unchanged. Independent review caught the inherited +00:00
default newly connected to strict administration receipt owners; the production
startup witness's explicit clock would otherwise hide that defect.

Corrected target run40582892453 established only the absent configuration
interface. This implementation is unvalidated pending review and the ordinary
gate. Runtime adapter capability/forwarding, management client selection and
trusted file/environment authoring remain later #341 work; this slice does not
claim those effects or an independently deployable dynamic installation.

This is the shared production and maintained-witness assembly of Operations
owners. `OperationsEffectPorts.secret_metadata_reader` carries the existing
Operations protocol into `DesiredGraphCommandService(secret_metadata_reader=...)`.
It does not invoke an action-free GraphAuthoring writer or manipulate private
preparation tokens. The service owns metadata timing, current fences, atomic
graph/action/receiver writes and exact original replay. Construction performs no
provider IO or durable writes; composition tests verify the actual forwarding.

#315 adds optional `delegation_key_generator` to the effect ports and explicit
`principal_authorizer` to the factory. Only when both exist does the factory
construct the accepted Operations generation service with its existing UoW and
clock. The authorizer is distinct from SecretUseAuthorizationService. The service
map always receives the optional generation value. Missing ports leave generation unavailable and construction still performs
no provider IO or durable mutation. The old exact-keyword test premise now includes
generation and explicitly asserts its default None, preserving all sharing laws.

#317 appends the optional Core SecretCustodian port. Only custody plus the explicit
independent principal authorizer constructs the existing Operations
SecretMaterialProvisionCommandService, using this same UoW and string clock. The
service map receives that owner or None; generation remains independently gated.
No route, schema, permission, retry policy or durable owner is introduced here.
The accepted provision owner retains current-policy checks, confidential decoding,
attempt transactions, custody dispatch and admission/history. Construction does
not invoke it. The existing exact-keyword fixture now includes the optional
provision value and requires None by default, retaining every sharing assertion.

Causal-red CI40029935612 reached three missing-port assertions in615 CPK methods;
later matrix/current-policy assertions and integrated preparation were unexecuted.
This implementation still requires source review and the normal full green gate.
## #351 provider-policy composition

An optional immutable provider-policy authority composes the accepted command,
current-read and public administration owners using one policy and one lazy exact
binding factory. Command history shares the existing UoW and clock. The existing
AUTHORIZATION family multiplexer separates this service from workspace admin;
no new semantic dispatch or authority store is introduced. Installation IDs must
agree when both policy families are configured. Construction acquires no provider
client or credential. The absent option preserves disabled owner behavior.
