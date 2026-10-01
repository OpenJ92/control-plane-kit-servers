Source: [bootstrap.contract.json](../../../../products/secrets_server/bootstrap.contract.json).

## Current receiving adoption (#237)

The receiving candidate selects Core and Operations
250d65e19dc748ebe840f705be77eb732dab3cb3, SDK
5dc93b92c27bb9bbe2af027f945a347e5e4131bc and Secrets
edfb8c0ebfc0cfcf3a667fb60d52b4a83bda1634. Its Interpreters runtime dependency is
accepted Interpreters I-M
bdbab01c0babaead958450b3c5e643317b2f4cd9, whose merge tree equals reviewed
I-C 6137017. Its shipped implementation is byte-identical to producer I-A.
The approved finite paired-gate exception retains S-B 9921911 as the final
Interpreters test witness. Earlier coordinates below are historical. This S-D
adoption still requires the unchanged whole Servers gate before merge.

The existing coordinate generator ran in repository policy Docker image
python:3.14-slim with network disabled and only this checkout writable. Canonical
upstream fields generate pyproject and six product recipes; published source/image
coordinates, product descriptors and both catalogue byte sets are unchanged.
Generation is not test green or image qualification. All existing gate stages,
installed provenance checks, source/historical witnesses and cleanup remain.

Source startup now supplies CPK_WRAPPER_CONFIGURATION_FILE for the existing
product-specific mounted 0444 public control file. Common receiver V2 is required;
no default key, private bootstrap rename, UID, port or listener change is made.

Historical context follows; the current adoption above governs selected dependencies.
Maintain with the source process ABI and product contract.

This adjacent bootstrap contract keeps the two private0400 master-key/credential inputs nonrecursive and outside the public product artifact. The source receiver additionally requires one separate public configuration_files entry: canonical path, environment name, JSON profile,65536-byte bound and0444 mode. The recipe supplies that fixed environment value; it is not a graph PublicStaticEnvironmentBinding because the accepted name is secret-shaped under Core's current rule. Public configuration provides no private provider credential or key. Historical published descriptors and baseline smoke do not acquire source receiver credit from this documentation.
