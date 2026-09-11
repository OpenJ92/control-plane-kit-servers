Source: [scripts/hello_server_image_smoke.sh](../../../scripts/hello_server_image_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This standalone smoke optionally builds Hello, starts a fixed-name container with loopback host publication and checks greeting HTML against render_hello from the same running image, empty dependency declarations and selected observer fields. Comparing against the image's own renderer verifies transport/configuration consistency but is not an independent rendering oracle. Empty dependencies do not exercise remote dependency health.

Before execution and on exit/signals, cleanup force-removes the fixed container name and suppresses errors, without exact-ID/ownership revalidation or final absence audit. Curl/Docker calls have no explicit per-call deadline here. The script's presence is not authority to run it against a shared name or to claim cleanup succeeded; current AGENTS and the owning validation plan still govern execution.

Related source and evidence: [products/hello_server/src/control_plane_kit_servers_hello_server/server.py](../../../products/hello_server/src/control_plane_kit_servers_hello_server/server.py), [scripts/hello_server_published_image_smoke.sh](../../../scripts/hello_server_published_image_smoke.sh), [test.sh](../../../test.sh).
