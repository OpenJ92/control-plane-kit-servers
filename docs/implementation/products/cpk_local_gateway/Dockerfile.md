Source: [products/cpk_local_gateway/Dockerfile](../../../../products/cpk_local_gateway/Dockerfile).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This image packages the gateway process and fixes its Core dependency to the
repository revision shown in the build recipe. It installs FastAPI, PyJWT with
crypto, uvicorn and psycopg using lower version bounds; the Python slim base is
tagged, not digest-pinned. A build therefore does not reproduce a complete
transitive environment solely from this file.

The product source is copied onto PYTHONPATH, the gateway user has UID 10005,
and the entrypoint runs server.main on port 8000. The empty default target map
grants no target access. Startup also requires explicit Ed25519 verifier
configuration; those settings are not supplied by this recipe. EXPOSE is image
metadata, not host publication, readiness, signed-probe evidence or a guarantee
of the runtime's filesystem/network restrictions.

Related source and evidence: [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py](../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/server.py), [products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py](../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/verification.py), [products/cpk_local_gateway/product.cpk.json](../../../../products/cpk_local_gateway/product.cpk.json).
