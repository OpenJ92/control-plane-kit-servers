Source: [Dockerfile.bootstrap](../../../../products/cpk_server/Dockerfile.bootstrap).

#301 extends the existing external acquisition driver, not the CPK service image.
Build USER0 precedes installing the existing selected Secrets dependency. Its
archive pin is generated from coordinates/server-products.json by the existing
coordinate owner. The Secrets product configuration source is copied alongside
CPK; PYTHONPATH retains CPK/gateway and adds Secrets. Runtime/helper entrypoints
stay unchanged. Only commissioning launch overrides UID/GID to the operator.

The full Servers test image already contains Secrets and cannot establish this
packaging connection. The existing actual-driver stage now imports image-owned
product modules, prepares isolated fixture trust and decodes both real receiving
artifacts before continuing legacy launcher plan/apply/public-setup checks.
No service image, published digest or product catalogue coordinate changes here.
