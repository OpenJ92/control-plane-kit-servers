Source: [products/secrets_server/Dockerfile](../../../../products/secrets_server/Dockerfile).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This image composes the external Secrets provider at the source commit selected
by the repository coordinates, with Uvicorn as its process launcher. The Python
base is a tag and Uvicorn has a lower bound; the source pin is not a fully
immutable dependency closure. Rebuilding this file does not establish the
published descriptor's image identity.

The image creates the secrets account with numeric UID 10006 and owner-only
bootstrap/data directories, then runs under that UID. It defaults the SQLite
path to the retained mount and the provider identity to control-plane-kit.
The entrypoint supplies bootstrap file paths; it does not embed their values.
Uvicorn binds HTTP to all container interfaces on 8081. EXPOSE does not publish
a host port or provide TLS.

The pinned provider's server module loads the key and credentials and admits
custody while constructing its module-level app. Those effects belong to the
Secrets repository; this image owns package selection, account/filesystem setup
and process invocation. Numeric account, HOME, protected-file and provider
behavior need the owning image witness, not only Dockerfile text assertions.

Related source and evidence: [coordinates/server-products.json](../../../../coordinates/server-products.json), [products/secrets_server/entrypoint.sh](../../../../products/secrets_server/entrypoint.sh), [products/secrets_server/bootstrap.contract.json](../../../../products/secrets_server/bootstrap.contract.json), [products/secrets_server/tests/live_numeric_bootstrap.py](../../../../products/secrets_server/tests/live_numeric_bootstrap.py).
