Source: [test_support/tests/test_gate_contract.py](../../../../test_support/tests/test_gate_contract.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This text-based contract reads test.sh from CPK_PACKAGE_ROOT or its repository-relative fallback. It checks executable/root anchoring, coordinate-check order before build, root/product integrity scope, the explicit source-image build flag and final residue-audit position.

These selected markers guard gate wiring; they do not execute the shell, prove every branch's status behavior or perform residue observations. The source and live fixtures remain the authority for actual phase/effect semantics. Changing the gate requires both source review and the owning executable workflow when authorized.

Related source and evidence: [test.sh](../../../../test.sh), [tests/test_docker_harness.py](../../../../tests/test_docker_harness.py).
