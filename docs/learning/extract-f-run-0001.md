# EXTRACT.F Run 0001

## #650 Server Repository Policy

#650 installs the first repository-local operating policy in
`control-plane-kit-servers`. The work is policy and documentation only: no
product implementation, package metadata, Docker harness, descriptor catalogue,
cpk-server process, or Hello transfer enters here. In short: no product
implementation enters #650.

Red proof:

```text
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  python -m unittest tests.test_repository_policy
```

Before implementation, the focused policy tests failed because `AGENTS.md`,
`GIT-FLOW.md`, `docs/product-layouts.md`, and this learning document did not
exist. The product inventory check already passed, proving #649 left the
repository empty of implemented products while reserving cpk-server and Hello.

Policy now established:

- one product owns one directory;
- catalogue imports declaration values, not applications or stores;
- core never imports servers;
- server products may import pinned core contracts;
- cpk-server and Hello have different roles;
- Docker-first validation is required;
- broad Docker prune is forbidden;
- shared support requires evidence from two products or an explicit bootstrap
  exception.

Handoff:

- #651 owns Python package metadata, root imports, pinned core dependency, and
  declaration-only catalogue entrance.
- #652 owns the canonical Docker-first test harness, image lanes, digest
  capture, and cleanup audits.
- #653 owns descriptor catalogue shape and deterministic publication artifacts.

No product implementation was added in #650.
