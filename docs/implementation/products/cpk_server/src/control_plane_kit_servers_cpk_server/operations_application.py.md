Source: [operations_application.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/operations_application.py).

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
