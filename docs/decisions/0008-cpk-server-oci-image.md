# 0008 cpk-server OCI Image

Status: Accepted

Issue: #815

Decision:

Package the cpk-server wrapper as a runnable OCI image using only the Python
standard library for the first process host. The image wraps the #814
framework-neutral HTTP/MCP boundaries rather than introducing a parallel route
or command model.

The image requires explicit bootstrap environment:

- `CPK_SERVER_MODE=execution-capable`
- `CPK_CONTROL_AUTH_CONFIGURED=true`
- `CPK_PORT=<1..65535>`

No database URL, auth token value, or runtime secret is baked into the image,
bootstrap contract, durable descriptor stub, or catalogue.

Consequences:

- The image runs as non-root user `cpk`.
- Missing bootstrap configuration fails before serving.
- Liveness and readiness are separate endpoints.
- HTTP and MCP smoke calls traverse the #814 boundaries.
- Product inventory may record an image definition, but catalogue publication
  remains empty until #816 provides descriptor/image/source digest evidence.
- The host-side smoke script builds/runs/removes only owned resources and then
  invokes the existing residue audit.

No recursive deployment, Hello image, cloud runtime interpreter, completed
descriptor, or catalogue declaration enters #815.
