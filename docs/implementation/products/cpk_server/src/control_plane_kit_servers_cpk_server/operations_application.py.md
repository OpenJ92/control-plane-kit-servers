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
map always receives the optional generation value; confidential provision stays
omitted. Missing ports leave generation unavailable and construction still performs
no provider IO or durable mutation. The old exact-keyword test premise now includes
generation and explicitly asserts its default None, preserving all sharing laws.
