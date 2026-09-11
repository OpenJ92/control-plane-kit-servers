Source: [products/secrets_server/bootstrap.contract.json](../../../../products/secrets_server/bootstrap.contract.json).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This adjacent document names the non-recursive inputs needed to start the root
Secrets provider: a database path under retained provider data, provider identity,
master-key file and API credential/grant file. It gives default mount targets,
0400 file modes and declared byte bounds. Bootstrap values are supplied by
trusted preflight infrastructure, outside the product descriptor and its
configuration artifacts.

This is descriptive contract data, not an executable filesystem or credential
validator. The shell entrypoint supplies path defaults; the selected Secrets
package owns actual key/credential loading and custody admission. Check those
consumer implementations when changing a bound or allowed value. Product tests
check selected declarations and the absence of recursive secret deliveries;
they do not prove every declared requirement is enforced.

A nested provider may receive equivalent files from an already admitted parent.
That possibility does not authorize resolving a root provider's bootstrap
through itself, or establish that any parent has admitted custody.

Related source and evidence: [products/secrets_server/product.cpk.json](../../../../products/secrets_server/product.cpk.json), [products/secrets_server/entrypoint.sh](../../../../products/secrets_server/entrypoint.sh), [products/secrets_server/Dockerfile](../../../../products/secrets_server/Dockerfile), [products/secrets_server/tests/test_secrets_server_product.py](../../../../products/secrets_server/tests/test_secrets_server_product.py).
