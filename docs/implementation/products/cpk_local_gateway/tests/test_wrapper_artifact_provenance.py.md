Source: [test_wrapper_artifact_provenance.py](../../../../../products/cpk_local_gateway/tests/test_wrapper_artifact_provenance.py).
Maintain this companion with the source and its artifact provenance contract.

Two focused regression tests call the same strict check used on actual Hello
container metadata. Source expectations come from the canonical source-build
coordinates; published expectations retain the fixed qualified artifact tuple.
The fixtures must differ, each mode accepts only its tuple, and cross-use,
missing/extra/substituted entries and unknown modes refuse. No Docker socket,
provider or credential is used by these tests. They do not simulate installed
evidence; the unchanged normal owning gate still checks actual containers and
the complete coupled scenario. Historical optional A/B semantics are unchanged.
