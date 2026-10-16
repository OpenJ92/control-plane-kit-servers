Source: [operations_application.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/operations_application.py).

This is the shared production and maintained-witness assembly of Operations
owners. `OperationsEffectPorts.secret_metadata_reader` carries the existing
Operations protocol into `DesiredGraphCommandService(secret_metadata_reader=...)`.
It does not invoke an action-free GraphAuthoring writer or manipulate private
preparation tokens. The service owns metadata timing, current fences, atomic
graph/action/receiver writes and exact original replay. Construction performs no
provider IO or durable writes; composition tests verify the actual forwarding.
