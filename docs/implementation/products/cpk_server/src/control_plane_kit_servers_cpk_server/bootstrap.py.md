Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This owner provides pure root-bootstrap planning, plan verification and the
narrow transition into external acquisition. It decodes closed root input,
builds the shared Docker installation topology, validates its graph and projects
resource names, image references, secret/file locators, retained volumes,
loopback binding and the ordered public setup routes. It requires explicit
runtime-access delivery and accepts external ingress only; it does not create
the external endpoint.

Canonical JSON and decoding are bounded at 1 MiB, reject duplicates/nonfinite
material and bind the plan to its canonical input and exact local driver ID.
verified_plan recomputes the whole projection and compares it plus the expected
digest; changing a resource, graph permission or driver cannot be accepted
merely by retaining an old digest. This is integrity against the supplied
reviewed coordinates, not an independent signature or authorization service.

The setup plan names workspace/provider/reference/runtime authority/delivery/
product/image-pull/ingress registrations through existing public commands.
Ingress's generated provider registration is an explicit result binding.
Required material includes the separate setup bearer and graph secret
deliveries; image-pull credential references are separately admitted by the
runtime material reader. Values remain references and locators during planning;
no secret file, Docker client or provider is read by plan_root_bootstrap.

matches_image_reference compares repository plus exact digest, admitting only
the explicit Docker Hub official-library spelling variants. It does not
compare digest alone, infer other registry aliases or contact a registry.
protected_file_owner delegates image USER validation only when secret files
actually need an owning UID.

BootstrapStage/Reason classify guarded failures into closed diagnostics.
Known exact error types/messages get fixed reasons; untrusted subclasses,
mutated attributes and arbitrary exception text are not serialized by
bootstrap_failure. Guards catch Exception and preserve an inner diagnostic;
BaseException interruptions pass through. Diagnostics are ephemeral refusal
classification, not an acquisition receipt or evidence that effects did or did
not occur. RootBootstrapError itself is not a general-purpose sanitizer.

Apply verifies first, dynamically imports the effect owner and delegates.
Inspect delegates receipt/provider observations without executing a plan.
No automatic adoption, rollback or retry is defined by this interface.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py), [products/cpk_server/tests/test_root_bootstrap.py](../../../../../../products/cpk_server/tests/test_root_bootstrap.py), [products/cpk_server/tests/test_root_bootstrap_diagnostics.py](../../../../../../products/cpk_server/tests/test_root_bootstrap_diagnostics.py), [products/cpk_server/tests/test_root_file_recipient.py](../../../../../../products/cpk_server/tests/test_root_file_recipient.py), [products/cpk_server/tests/test_root_image_reference.py](../../../../../../products/cpk_server/tests/test_root_image_reference.py), [pyproject.toml](../../../../../../pyproject.toml).
