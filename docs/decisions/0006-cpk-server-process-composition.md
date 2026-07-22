# 0006 cpk-server Process Composition

Status: Accepted

Issue: #813

Decision:

Create `products/cpk_server` as the first product-local cpk-server wrapper
surface. The product package imports the pinned `control-plane-kit-core` handoff
contracts and composes one `CpkServerEntrypointHandoffContract` through a
product-local `CpkServerComposition`.

This issue deliberately stops before HTTP/MCP route implementation, Docker image
packaging, descriptor publication, and live recursive deployment.

Consequences:

- `control-plane-kit-core` remains independent and does not import this server
  repository.
- The root `control_plane_kit_servers` import still does not import cpk-server.
- HTTP and MCP remain contracts over the same program boundary.
- Execution-capable composition requires explicit auth configuration.
- Process-local target and observer state is immutable application state and
  does not own graph truth, activity history, approval truth, or execution
  truth.
- Hello cannot satisfy cpk-server laws.

No route server, OCI image, completed descriptor, or catalogue declaration enters
#813.
