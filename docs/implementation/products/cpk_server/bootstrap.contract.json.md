Source: [products/cpk_server/bootstrap.contract.json](../../../../products/cpk_server/bootstrap.contract.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This descriptive startup contract names execution mode, port, four database
requirements and optional selections for authentication, interpreters, secret
material, gateway signing and public DNS. It keeps runtime secrets, store
addresses and provider routes out of product descriptors. Selecting provider
material resolution names a path for admitted secret references; it is not
itself a grant to resolve them.

Actual admission belongs to server.py and its imported bootstrap contracts.
The JSON is neither a validator nor an exhaustive list of current process
inputs: the source also accepts the static-principals input and gateway grant
lifetime. The four store roles are separate topology requirements, while the
current operations_database_url check requires them to name one instance
database. Documented roles do not imply four independently supported stores.

The source requires authentication at the process boundary; verifier/credential
and exact-workspace grants must be composed explicitly. Secret-free descriptive
wording is not proof of global log redaction or startup success. Compare this
contract with the parser, installation composition and tests when those inputs
change; product tests inspect selected declarations rather than executing this
document as a schema.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py](../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py), [products/cpk_server/tests/test_image_bootstrap.py](../../../../products/cpk_server/tests/test_image_bootstrap.py), [products/cpk_server/product.cpk.json](../../../../products/cpk_server/product.cpk.json).
