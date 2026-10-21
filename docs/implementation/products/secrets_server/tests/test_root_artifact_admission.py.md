Source: [test_root_artifact_admission.py](../../../../../products/secrets_server/tests/test_root_artifact_admission.py).

#191 focused targets for the closed optional CPK/Secrets artifact pair. The proposed
bounded script owner is `scripts/root_artifact_inputs.py`: `select_root_artifacts`
returns None for empty/default selection or the exact mode/source/images mapping;
`qualify_root_artifact` validates role/reference/source against raw selected-image
metadata and optional prior execution ID; `require_root_artifact_provenance`
checks actual direct_url records against the gate-selected canonical cohort.
Invalid observations use one fixed `RootArtifactError`, never input material.

Six methods cover complete/default/partial inputs, strict role repositories and
digest/source syntax, distinct reference versus execution identity, cache drift,
platform/user/source metadata, and actual archive/subdirectory provenance. Source
revision labels are tested as metadata, not independent producer authorization.
Producer/gate equivalence remains the separately reviewed effect packet.

All #191 targets are grouped in the existing Secrets suite, which owns the joint
CPK/Secrets numeric-bootstrap witness. This lets the unchanged ordinary runner
execute the full focused target set in one suite instead of stopping at an earlier
root-suite failure before the Secrets cleanup targets. No runner is changed.

Missing owner assertion is intended missing-behavior red; collection imports no
future implementation. The target suite does not run host Python, Docker or a
registry. It executes only as part of the established Docker package gate.
