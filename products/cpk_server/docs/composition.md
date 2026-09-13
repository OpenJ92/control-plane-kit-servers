# cpk-server Composition Root

#813 creates only the process-composition surface for `cpk-server`. It consumes
`control_plane_kit_core.operations.CpkServerEntrypointHandoffContract` and binds
it to a product-local configuration and process-state model.

This is not the HTTP/MCP server implementation, Dockerfile, OCI image, or
completed product descriptor. Those belong to later EXTRACT.F issues.

## Installation topology

See [Shared Docker installation value](installation.md) for the pure CPK +
PostgreSQL + Secrets topology consumed by future bootstrap and public clients.

### HTTP host preparation (Servers199)

The standard FastAPI host registers each literal Core operator prefix (currently
/workspaces), including its exact and descendant paths. The unchanged neutral
boundary owns route matching, authentication, bounded payload/query decoding and
service dispatch. Exact legacy health/MCP handlers retain precedence; literal
fallthroughs and application-only framework404/405 projection preserve prior
unknown-route, method and slash responses. Decoded __control paths keep actual
SDK/framework responses in composition tests. The root wildcard is removed.

Root and CPK source builds install the canonical SDK[fastapi] dependency. This
prepares hosting without enabling production control routes or changing schema
startup or receiving inputs. The dependent Servers200 child owns that integration.
