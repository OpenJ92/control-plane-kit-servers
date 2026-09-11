Source: [products/cpk_server/tests/live_numeric_bootstrap.py](../../../../../products/cpk_server/tests/live_numeric_bootstrap.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This helper exercises the CPK image as a protected-file recipient inside an
owning numeric-bootstrap Docker fixture. The caller supplies the engine/SDK,
run labels, resource ledger, selected image and network; the helper checks image
run-label membership and numeric UID 10001 before creating a secret volume and
recipient container.

It generates ephemeral material, materializes it as owner-read-only, and checks
regular-file/UID/mode/content digest evidence. The recipient runs with the
image's default user, without a user/group override. Its probe checks the cpk
account, effective UID/GID, HOME access, mounted file ownership/digest and write
refusal. Container inspection checks exact image/configured USER/read-only
secret mount; wait is bounded and selected log tail must omit the generated
value.

This is a recipient/file-account witness, not the CPK server entrypoint,
control authentication or Docker-socket permission test. It appends obtained
resources to the caller's cleanup ledger but performs no cleanup itself; a
failed creation before identity capture remains the fixture's uncertainty.
SDK materialization helpers have their own lifecycle. No result from merely
reading this source is live validation evidence.

Related source and evidence: [products/cpk_server/tests/live_root_bootstrap.py](../../../../../products/cpk_server/tests/live_root_bootstrap.py), [products/cpk_server/tests/test_image_bootstrap.py](../../../../../products/cpk_server/tests/test_image_bootstrap.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py).
