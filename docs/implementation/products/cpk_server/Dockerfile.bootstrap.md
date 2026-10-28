Source: [products/cpk_server/Dockerfile.bootstrap](../../../../products/cpk_server/Dockerfile.bootstrap).
Maintain this companion alongside its source and selected dependencies.

For #341, the unchanged coordinate generator renders this recipe's existing
dependency subset from the accepted Core/Operations `4cc1716b`, Interpreters
`bd08b931`, SDK `464df26c`, Secrets `067678fb` cohort. Full hashes live in
the canonical manifest. Extras, base images, process behavior and published
identities stay unchanged. The released owning-gate retry is pending.

## Current #313 dependency adoption

For #313, existing generated dependency URLs select the accepted cohort in `coordinates/server-products.json`. Package subsets/extras, recipe behavior, base images and process identities are unchanged. This source dependency adoption does not change historical published product identities or enable confidential intake. Normal owner CI must establish installed compatibility.

Earlier checkpoint accounts below describe their named historical selections; they are not the current cohort or acceptance status.

Source: [Dockerfile.bootstrap](../../../../products/cpk_server/Dockerfile.bootstrap).

#301 extends the existing external acquisition driver, not the CPK service image.
Build USER0 precedes installing the already accepted Core/Operations/SDK/
Interpreters/Secrets cohort. The actual test.sh driver base is the historical
published CPK image (3ffc495), so installing only Secrets would leave old
Operations/Interpreters alongside new Core/SDK. Explicit archive pins are
generated from coordinates/server-products.json by the existing coordinate owner.
The pinned install uses --force-reinstall: the historical packages have the same
0.1.0 version, and pip otherwise collects the new archives without replacing
already-installed Core/Operations/Interpreters. This also reinstalls resolved
dependencies; installed provenance and the complete legacy driver gate must
both pass. Pins and requested extras remain unchanged.
The Secrets product configuration source is copied alongside
CPK; PYTHONPATH retains CPK/gateway and adds Secrets. Runtime/helper entrypoints
stay unchanged. Only commissioning launch overrides UID/GID to the operator.

The full Servers test image already contains Secrets and cannot establish this
packaging connection. The existing actual-driver stage now imports image-owned
product modules, prepares isolated fixture trust and decodes both real receiving
artifacts and checks installed direct_url.json provenance for the full cohort
before continuing legacy launcher plan/apply/public-setup checks.
No service image, published digest or product catalogue coordinate changes here.
# Managed PostgreSQL driver dependency (#327)

The external driver also copies the PostgreSQL product's authoring/readiness
package and adds it to its PYTHONPATH. This supports managed descriptor validation
and the existing bounded SQL invocation. It does not alter the running CPK or
Secrets images, install a PostgreSQL server into the driver, change pins, or
publish an image. The existing actual-driver witness imports this image-owned
package and plans a managed PostgreSQL installation with public fixture trust.

#349 selects accepted Core and Operations `fec0816281aeb83ede98616adcc4f96dfe5777a8`
through the existing coordinate generator. The tuple adds authorized workspace
product list/detail while preserving the accepted optional fresh-only schema
admission. SDK, Secrets and Interpreters pins are unchanged. This source selection
is not a published-image or live-adoption claim. Concurrent bootstrap integration
must retain newer accepted pins and initialization behavior.
