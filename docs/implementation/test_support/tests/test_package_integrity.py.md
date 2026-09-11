Source: [test_support/tests/test_package_integrity.py](../../../../test_support/tests/test_package_integrity.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests create temporary synthetic package, gate and approval files and inspect the scanner's report/finding codes. They exercise collection aliases, hidden tests, skip admission, placeholders, swallowed exceptions, legacy imports, option-name checks and mock reporting. Synthetic source is parsed as input; it is not an alternative execution of the application suite.

Keep scanner policy and its negative cases coordinated. Passing this file establishes selected scanner behavior, not real Servers authority, runtime cleanup or live acceptance.

Related source and evidence: [test_support/package_integrity.py](../../../../test_support/package_integrity.py), [test.sh](../../../../test.sh).
