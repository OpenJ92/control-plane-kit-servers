Source: [products/secrets_server/entrypoint.sh](../../../../products/secrets_server/entrypoint.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This strict POSIX shell wrapper supplies default paths for the master-key and
credential files when their environment variables are unset or empty, exports
both names, and replaces itself with the supplied command through exec.

It does not read, create, copy, chmod or validate those files. It also does not
initialize custody or authenticate requests. The Dockerfile's default Uvicorn
command imports the selected provider server, which owns those startup checks.
An explicit nonempty path remains unchanged. Keep these path defaults aligned
with the bootstrap contract and actual mounted file targets.

Related source and evidence: [products/secrets_server/Dockerfile](../../../../products/secrets_server/Dockerfile), [products/secrets_server/bootstrap.contract.json](../../../../products/secrets_server/bootstrap.contract.json), [products/secrets_server/tests/test_secrets_server_product.py](../../../../products/secrets_server/tests/test_secrets_server_product.py).
