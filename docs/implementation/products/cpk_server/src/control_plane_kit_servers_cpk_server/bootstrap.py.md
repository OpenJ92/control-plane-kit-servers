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
