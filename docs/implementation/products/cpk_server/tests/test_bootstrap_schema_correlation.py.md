Source: [test_bootstrap_schema_correlation.py](../../../../../products/cpk_server/tests/test_bootstrap_schema_correlation.py).

These tests cover the archive installer's behavior before workspace initialization.

- Return the existing archive commit and SQL digest only when the imported file
  belongs to the Operations distribution and matches its single SHA-256 RECORD entry.
- Refuse changed SQL, shadow resources, invalid RECORD metadata and local directory origins.
- Require a regular opened file and enforce the recorded size when supplied.
  A larger fixture checks the entire digest when the RECORD omits its optional size.
- Report schema ownership and earlier target refusals separately before recording
  helper intent or creating Docker resources. Public diagnostics contain fixed tokens.

The source tests exercise these boundaries with disposable distribution metadata
and Docker observations. Packaged driver verification uses the actual helper UID.
