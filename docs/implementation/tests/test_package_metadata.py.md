Source: [tests/test_package_metadata.py](../../../tests/test_package_metadata.py).
Maintain this companion with root packaging and dependency adoption.

Metadata tests require exact Core, Operations, Interpreters and SDK[verification]
requirements from the canonical manifest. The isolated installed process reads
each distribution's direct_url.json and compares archive URL/subdirectory to
those coordinates, then imports SDK stdlib, health and verification interfaces.
This runs inside the owning Python3.12 Dockerfile.test environment after normal
pip resolution. Missing distributions, wrong pins or unavailable optional crypto
imports fail the test; no fallback installation or local override is attempted.

Existing lightweight root/catalogue and process-import separation assertions
remain. The import witness starts no SDK listener and does not duplicate SDK
authorization matrices. Installed source compatibility is distinct from a
product's Dockerfile composition, published digest or health capability.
