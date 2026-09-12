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

Servers #177 synchronizes this Core-only mirror to canonical CPK merge `e3e29995a4ffc6e6645c2b35d41f394438464d2d`. The accepted #176 correction makes the replay cache own atomic clock observation and admission. Servers #163 adopts published gateway image `sha256:6131135d8bf37c259fb1e8ac314896889a87e15b402e9d49e50c9ed86023c430` from producer `1ae09241bac25d48ca5ebb621bce3239d3035e10`. Its digest-bound structural-grant witness passed, establishing installed compatibility only; source tests protect replay-negative laws, and the separate live signed probe remains pending. The [acceptance recipe](../../../../products/cpk_server/examples/child_api_acceptance.md) records publication and qualification evidence.
