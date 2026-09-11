Source: [test.sh](../../test.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

## Owning sequence

This script anchors to the repository root and performs coordinate checks, test-support/integrity checks, a package test-image build/run and outside-/app import check. The ordinary package container is socket-free. Later phases explicitly receive local Docker authority for source-built numeric file witnesses, selected source/published image smokes and an external-root bootstrap fixture. The final project-label residue audit is a separate last phase; an earlier package success is not full gate completion.

The numeric controller requires a local Unix context, rejects TLS/remote context settings, captures engine/image/resource identities and creates an internal test network. Its EXIT handler preserves the triggering status and makes cleanup failure nonzero. Controller/network cleanup checks exact IDs and ownership labels; temporary image tags are matched to recorded IDs and run labels. This is scoped fixture cleanup, not authority to remove arbitrary resources with similar names.

## Delegated effects and retained evidence

The root-bootstrap phase builds a temporary launcher, prepares isolated inputs, invokes bootstrap.sh plan/apply with the explicit plan digest, checks the result and verifies completed acquisition cannot be redispatched. Its finally path delegates resource cleanup to the owning fixture and checks launcher image identity before tag removal. Private diagnostic records can be retained. Read the fixture/launcher owners before inferring more detailed cleanup, retry or history guarantees.

Image selection and build flags distinguish source-built from published coordinates. Build/pull/install work can use networks; local runtime probes and temporary stores are effects even without Cloudflare/DNS exposure. This baseline does not include the held child API acceptance harness from #173. No grandparent/child completion or historical retry permission follows from this gate's source or a narrower phase result.

Use only the authorized owning workflow. Documentation authoring did not run this script, regenerate coordinates, launch containers or access credentials.

Related source and evidence: [scripts/run_all_tests.py](../../scripts/run_all_tests.py), [scripts/docker_residue_audit.sh](../../scripts/docker_residue_audit.sh), [products/secrets_server/tests/live_numeric_bootstrap.py](../../products/secrets_server/tests/live_numeric_bootstrap.py), [products/cpk_server/tests/live_root_bootstrap.py](../../products/cpk_server/tests/live_root_bootstrap.py), [bootstrap.sh](../../bootstrap.sh), [test_support/tests/test_gate_contract.py](../../test_support/tests/test_gate_contract.py), [tests/test_docker_harness.py](../../tests/test_docker_harness.py).
