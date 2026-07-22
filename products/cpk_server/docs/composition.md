# cpk-server Composition Root

#813 creates only the process-composition surface for `cpk-server`. It consumes
`control_plane_kit_core.operations.CpkServerEntrypointHandoffContract` and binds
it to a product-local configuration and process-state model.

This is not the HTTP/MCP server implementation, Dockerfile, OCI image, or
completed product descriptor. Those belong to later EXTRACT.F issues.
