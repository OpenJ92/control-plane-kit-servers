# 0001 Repository Foundation

Status: Accepted

Context:

`control-plane-kit-core` now owns the pure graph, planning, contract, and
operation-handoff language. Server products need a separate repository so the
core package stays importable without product processes, FastAPI apps, Docker
images, or server-specific optional dependencies.

Decision:

Create `OpenJ92/control-plane-kit-servers` as a public repository with `main`
as the default branch and `develop` available for later release flow. The first
commit after repository creation records coordination metadata only:

- pinned core release-candidate coordinates;
- empty product inventory;
- #804 cpk-server control-process handoff summary;
- issue-transfer strategy;
- security/foundation review.

Consequences:

- No product implementation enters during repository creation.
- `products/cpk_server` and `products/hello` are reserved but not created as
  implementation directories yet.
- #650 owns the server-repository AGENTS and operating loop.
- #651 owns Python package metadata and import surfaces.
- #652 owns Docker-first test/image harnesses.
- #653 owns the public descriptor catalogue shape.

Laws:

- Core never imports servers.
- Server products may import pinned core values and contracts.
- One product owns one directory.
- Catalogue imports values, not applications or stores.
- cpk-server and Hello are distinct products with distinct obligations.
