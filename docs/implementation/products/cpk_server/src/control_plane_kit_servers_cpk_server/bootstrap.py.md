Source: [bootstrap.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py).

The pure root projection compiles the existing installation value, validates its
graph, and derives the inspectable acquisition plan. Each node's
`configuration_files` carries the complete compiled artifact descriptor, exact
target, SHA256 of UTF-8 content, and a deterministic volume name separated from
secret-file names. Public configuration does not add protected material inputs.
Saved-plan validation recompiles from input and compares the whole plan plus its
digest; changed content, mode, path, digest or resource names cannot be applied.
Older projections require explicit regeneration/review, not automatic upgrading.

Closed diagnostic tokens suppress provider bodies and private exception values.
Configuration mode/user refusal uses `configuration-user-unsupported` within
product-image verification. This module performs no Docker/provider effects.

Servers #297 adds only an optional full Core artifact descriptor at
`installation.managed_health_configuration`. Absence passes None; present null
or malformed/digest-inconsistent descriptors are refused. The shared installation
owner checks the fixed managed-health profile and original contract conflicts.
Existing graph projection delivers the artifact without changing acquisition,
receipts, mount materialization or schemas. Content and source metadata remain
exact; input and repeated plan content still must fit the existing 1 MiB bound.

#302 adds only the optional website-enabled branch. Core's image codec and the
accepted composer own the website. Actual Core selection and CPK/Secrets
decoders own receiving semantics; root admission checks fixed role slots, byte
bounds and installation coordinates/distinct supplied receiver IDs. It never
reserializes admitted artifact content. The plan derives two loopback records
and appends the actual website document to canonical-input backend setup order.
Absent input passes no new constructor argument, imports no enabled-only owner,
adds no fields and retains the original three-import count before digesting.
This source branch comparison, not the target self-roundtrip alone, establishes
the intended historical byte preservation; the full owning gate remains required.
