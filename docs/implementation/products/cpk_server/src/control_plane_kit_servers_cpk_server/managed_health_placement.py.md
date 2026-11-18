Source: [managed_health_placement.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/managed_health_placement.py).

The existing static selector accepts scoped borrowed Docker clients or immutable
acquisition policies. #341 adds a separate typed dynamic mode: the trusted
ManagedRuntimeCapabilityPolicy, an exact immutable installed catalog, and the
existing UoW factory. DockerRuntimeCapabilityBinding pairs the owner's opaque
capability value with the Interpreter's fixed Unix acquisition configuration.
Nested values are validated; duplicate/mismatched catalogs or mixed static inputs
are rejected with bounded errors. An explicit empty policy/catalog is dynamic;
absent dynamic inputs preserve the static positional API. The64 bound counts
installed capabilities, never workspaces. Representations omit private transports.

Construction composes the actual ManagedRuntimeSelectionService without opening
the UoW. Each dynamic select uses its current point lookup; that owner alone
checks installation, registration, assignment and policy. Servers maps the
returned capability ID to its installed configuration and returns the existing
scoped DockerRuntimePolicyBinding. There is no grant cache, workspace enumeration,
fallback, Docker construction or provider call. Unavailable/denied lookup returns
no selection. Existing static selection and gateway endpoint behavior remain.

The returned transport configuration is not admission authority. Later execution
must bind the actual acquired capability to C's admitted ManagedRuntimeSelection;
it may not independently select a different capability after admission. Current
ManagedHealthProcessConfiguration's static guard remains untouched. Process
authoring, full semantic forwarding and live qualification remain later work.

Target run40592857952 reached only the absent binding-interface assertion in two
tests. This implementation is pending independent source review and the unchanged
owning Linux gate, including actual public/PostgreSQL management selection proof.
