# 0007 cpk-server HTTP And MCP Boundaries

Status: Accepted

Issue: #814

Decision:

Introduce framework-neutral HTTP-shaped and MCP-shaped process boundaries for
`products/cpk_server`. Both boundaries interpret the core contracts exposed by
`CpkServerComposition` and dispatch through one shared
`CpkServerApplicationBoundary`.

This issue deliberately does not introduce FastAPI, Uvicorn, hosted MCP process
machinery, Docker image packaging, or a second command/read vocabulary. Those
belong to later wrapper/image issues.

Consequences:

- HTTP and MCP requests resolve against the same core route IDs.
- Reads and commands call the same application service objects.
- Missing authorization, unknown operations, malformed JSON, and oversized
  bodies fail before service dispatch.
- Error payloads are bounded and do not echo authorization headers.
- Hosted cpk-server hardens the old development fixture behavior: mutation-
  capable operation requires configured authentication; unauthenticated mutation
  mode is not preserved.
- Application-block data routes remain outside cpk-server; operator control auth
  does not define opaque application traffic behavior.

No route server, OCI image, completed descriptor, or catalogue declaration enters
#814.
