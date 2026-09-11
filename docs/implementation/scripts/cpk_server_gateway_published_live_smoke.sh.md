Source: [scripts/cpk_server_gateway_published_live_smoke.sh](../../../scripts/cpk_server_gateway_published_live_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This opt-in launcher builds a source controller, runs coordinate consistency,
then selects five product digest references and the gateway source commit via
the coordinate helper. Downstream product builds are disabled; the controller
build remains an effect.

PLAN_ONLY occurs after that build and containerized coordinate check. It prints
coordinates without product pulls or live dispatch, but is not effect-free.
Selection and a digest-pattern shell check do not independently verify remote
manifest bytes, image contents or source parity.

Normal execution pulls the products, selects gateway-verifier-projection and
delegates credentials, provisioning, scenario evidence and cleanup to the
source-live launcher. The residue audit runs only after that launcher succeeds.
This wrapper has no independent cleanup trap.

Related source: [coordinate selector](product_image_coordinate.py.md),
[coordinate consistency](apply_coordinates.py.md),
[source-live launcher](../../../scripts/cpk_server_secret_provider_source_live_smoke.sh),
[residue audit](docker_residue_audit.sh.md).
