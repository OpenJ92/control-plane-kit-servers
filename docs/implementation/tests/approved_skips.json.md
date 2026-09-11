Source: [tests/approved_skips.json](../../../tests/approved_skips.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

The empty approval list permits no conditional skip exceptions. The integrity scanner matches entries by exact test identity/reason and rejects duplicate, stale, unconditional and literal-condition skip forms according to its own rules. Editing this data is not authority to weaken acceptance; any changed exception must be reviewed under the governing test policy.

Related source and evidence: [test_support/package_integrity.py](../../../test_support/package_integrity.py), [test_support/tests/test_package_integrity.py](../../../test_support/tests/test_package_integrity.py), [AGENTS.md](../../../AGENTS.md).
