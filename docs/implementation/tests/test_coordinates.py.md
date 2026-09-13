Source: [tests/test_coordinates.py](../../../tests/test_coordinates.py).
Maintain this companion with the coordinate contract.

Tests compare generated files with the canonical manifest, preserve published
product source/digest behavior and verify required canonical SDK commits.
Synthetic distinct upstream replacements must reach all current dependency
destinations while leaving generated product descriptors/catalogue byte-identical.
This detects hard-coded or omitted replacements independently of the currently
selected commits. Hello #184 adds its SDK-only generated destination and explicit
verification-extra installation assertion. Existing published-image and Secrets provenance assertions
remain intact. These tests execute in the normal Docker-backed ./test.sh and
do not claim that an image was built, published or deployed.

Servers185 extends the existing synthetic SDK drift destination set and explicit
SDK[verification] recipe assertion to the active-router Dockerfile. Published
product descriptors remain byte-preserved; no image coordinate is advanced.
