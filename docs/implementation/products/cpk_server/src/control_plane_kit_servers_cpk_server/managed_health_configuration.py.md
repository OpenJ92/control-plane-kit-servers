Source: [managed_health_configuration.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/managed_health_configuration.py).

Servers #294 owns a frozen process value and a closed JSON decoder. One exact
Unix policy is shared by every policy binding; borrowed clients cannot enter
this process format. The existing selector owns scope identity and duplicate
validation, the product codec owns canonical documents, the receiver adapters
own gateway transit slots, and the pure native qualifier owns its configuration.
Native plan/proof qualification still occurs at selection/observation time.

Input is exact bytes, at most 1 MiB, with 1–64 scopes and gateway documents.
Nested duplicate keys, nonfinite numbers, missing/unknown keys and malformed
types are rejected. Distinct product references may belong to the same family.
Errors are fixed and raised outside exception handlers; repr hides fields.

The reader validates a bounded absolute path and opens it once with NOFOLLOW,
CLOEXEC and NONBLOCK. It checks regular-file type and initial size on that same
descriptor, reads at most limit+1 bytes and closes in finally, including
interruption. A final-component symlink is refused; ancestors must be trusted.
There is no new file ownership/mode rule or total I/O deadline. Restart is
required to load changed configuration. No provider credential is opened here.

See [startup example](../../../../managed-health-startup.md) for the complete
fixture-derived format and its source-only evidence limits. Targets and source
review/owning gate coordinates are recorded on PR296; this companion does not
claim green validation or live deployment before those gates complete.

Servers #297 adds `managed_health_configuration_artifact(raw)` and constants for
the fixed `cpk-managed-health` JSON/0444 installation slot. The constructor keeps
outer UTF-8 bytes intact and reuses the process decoder. Core owns the smaller
262,144-byte artifact bound, content validation, content digest and provenance
syntax. Direct typed artifacts are round-tripped through Core's descriptor
decoder before installation use, catching corrupted digest metadata. Distinct
valid source digests survive as metadata, not authenticity claims. Delivery
errors use the separate fixed installation message outside caught context;
the accepted standalone decoder and reader behavior remain unchanged.

#341 adds a separate closed v2 process schema with capability_ids instead of
static workspace/runtime/authority scopes. The immutable value keeps exact
DockerRuntimeCapabilityBinding values sharing the installed local policy and
provider_clients=None. It has no UoW or callable placeholder. The process
composition binds the existing dynamic selector to its actual UoW only after
the installation receipt guard. Existing v1 inputs retain their static selector.

The public artifact helper retains its v1-only default. #345 adds explicit v2
artifact consumption only at the dynamic installer entrance, with its separate
private workspace-policy delivery obligation. Static installations still refuse
v2 and dynamic installations refuse v1 mixed mode. Core metadata/bounds and exact
content bytes remain unchanged. The complete catalogue is compared with private
policy during admission. Public dynamic apply remains incomplete before Docker
until #346/#347 are composed; authoring is not full bootstrap acceptance.
