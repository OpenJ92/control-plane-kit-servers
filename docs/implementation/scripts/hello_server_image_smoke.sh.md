Source: [hello_server_image_smoke.sh](../../../scripts/hello_server_image_smoke.sh).

This is a historical unwrapped published-image witness used by
hello_server_published_image_smoke.sh. It requires an explicit immutable image
reference and rejects source builds before creating or cleaning Docker resources.
Its legacy readiness check belongs to that image's unchanged published descriptor.
Current wrapped Hello requires local public configuration and SDK health; this
script does not qualify that source or provide compatibility routes for it.
The existing exact named smoke cleanup is unchanged; no broad cleanup is added.
