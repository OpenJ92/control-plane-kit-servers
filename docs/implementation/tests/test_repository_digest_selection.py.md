Source: [test_repository_digest_selection.py](../../../tests/test_repository_digest_selection.py).

Please update alongside its source file. The selected repository is now Hello;
the original repository-selection and rejection laws are preserved.

The normal Docker-backed package suite invokes the actual pure shell selector
with text input. Exact requested repository selection must be order-independent;
absent, wrong repository, duplicate/multiple, malformed length/algorithm/case
inputs must exit nonzero without emitting a witness. Tests do not stub Docker,
perform a push, access credentials or assert private package visibility.
