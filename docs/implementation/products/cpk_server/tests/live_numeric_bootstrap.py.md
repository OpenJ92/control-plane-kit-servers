Source: [live_numeric_bootstrap.py](../../../../../products/cpk_server/tests/live_numeric_bootstrap.py).

The established numeric bootstrap fixture stages a synthetic credential and a
synthetic private workspace policy through the existing SDK protected-file owner.
It verifies image UID 10001, regular 0400 files, exact content digests and the
complete read-only subpath mount set. A process using the actual image's default
user reads the policy with the accepted decoder and cannot write either file.
The same recipient is restarted with the retained policy volume and checked again.
All added resources use the fixture's existing exact-ID cleanup list and labels.

This is component staging/decoder/restart evidence when the owning suite reaches
it. It does not bypass the dynamic root apply stop, initialize a store, grant
permissions or establish parent bootstrap acceptance. Policy/credential content
and the private synthetic subject must not appear in recipient logs.
