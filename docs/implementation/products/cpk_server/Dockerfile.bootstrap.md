Source: [Dockerfile.bootstrap](../../../../products/cpk_server/Dockerfile.bootstrap).

#301 extends the existing external acquisition driver, not the CPK service image.
Build USER0 precedes installing the already accepted Core/Operations/SDK/
Interpreters/Secrets cohort. The actual test.sh driver base is the historical
published CPK image (3ffc495), so installing only Secrets would leave old
Operations/Interpreters alongside new Core/SDK. Explicit archive pins are
generated from coordinates/server-products.json by the existing coordinate owner.
The Secrets product configuration source is copied alongside
CPK; PYTHONPATH retains CPK/gateway and adds Secrets. Runtime/helper entrypoints
stay unchanged. Only commissioning launch overrides UID/GID to the operator.

The full Servers test image already contains Secrets and cannot establish this
packaging connection. The existing actual-driver stage now imports image-owned
product modules, prepares isolated fixture trust and decodes both real receiving
artifacts and checks installed direct_url.json provenance for the full cohort
before continuing legacy launcher plan/apply/public-setup checks.
No service image, published digest or product catalogue coordinate changes here.
