Source: [test_support/package_integrity.py](../../../test_support/package_integrity.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This AST/regex scanner reports selected unittest collection, skips, placeholders, swallowed exceptions, legacy imports and proof-changing gate options. It records mocks as evidence rather than rejecting all mock use. Conditional skip approval requires the exact test identity and reason; unconditional/literal-condition skips and stale approvals remain findings.

Static discovery is not executed-test count or behavioral adequacy. The scanner neither executes product tests nor proves arbitrary dynamic imports/shell flow safe. Diagnostic findings may include source paths or parse-error text, so this is a repository tool rather than a public redaction API. Its CLI returns a failing status when findings exist; test.sh supplies root and product scan scope.

Related source and evidence: [test.sh](../../../test.sh), [test_support/tests/test_package_integrity.py](../../../test_support/tests/test_package_integrity.py), [tests/approved_skips.json](../../../tests/approved_skips.json).
