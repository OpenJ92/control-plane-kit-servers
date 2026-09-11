Source: [scripts/docker_residue_audit.sh](../../../scripts/docker_residue_audit.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This read-only Docker query checks containers, networks and volumes carrying the exact Servers project label and fails if any are listed. It deletes nothing. The label is a query scope, not cryptographic ownership or permission to clean up the returned resources.

The audit covers all resources in that label scope, not only the current test run. It does not inspect images, unlabeled helpers, registry state or retained files, and sequential queries are not an atomic absence snapshot. Printed names/status are operational diagnostics; a passing result is absence in these selected query surfaces at observation time, not universal cleanup proof.

Related source and evidence: [test.sh](../../../test.sh), [tests/test_docker_harness.py](../../../tests/test_docker_harness.py).
