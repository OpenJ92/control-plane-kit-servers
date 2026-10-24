Source: [test_image_cleanup_reporting.py](../../../../../products/secrets_server/tests/test_image_cleanup_reporting.py).

#191 strengthens the existing Secrets smoke finish boundary. Tests source the
actual script's declarations/functions/trap before its first image-build branch,
then exercise normal and failed exit using controlled Docker responses. They do
not copy cleanup code or simulate a full provider startup.

The cases require successful authoritative inventories and private-file cleanup
before exactly one final PASS; failed inventory/removal and retained residue stay
failure; prior primary failure survives successful cleanup; no ambiguous removal
is retried and no image is removed. Existing unique run-label scope remains.
The same scenarios independently cover container, volume and network inventories,
removal, residue, and failed post-cleanup absence inventory. This avoids proving
only the container path while masking the independent volume/network pipelines.
CPK's already-authoritative final residue audit is outside this correction.

All subprocess execution belongs to the established Docker package tests. No host
test execution, real Docker command, production credential or provider effect is
performed by these targets.
