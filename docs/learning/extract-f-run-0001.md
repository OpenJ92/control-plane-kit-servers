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

## #651 Package Metadata And Catalogue Entrance

#651 creates the first installable Python package surface for
`control-plane-kit-servers` without adding any product implementation.

Red proof:

```text
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  python -m unittest tests.test_package_metadata
```

Before implementation, the focused tests failed because `pyproject.toml` and
`src/control_plane_kit_servers` did not exist.

Package decisions:

- package name: `control-plane-kit-servers`;
- package version: `0.1.0`;
- pinned core dependency:
  `control-plane-kit-core @ https://github.com/OpenJ92/control-plane-kit/archive/a04631770efbf59e62b4536cc80a71d42873446d.zip#subdirectory=control-plane-kit-core`;
- root import exports only `__version__` and `load_catalogue`;
- `load_catalogue()` returns `()` until #653 defines completed descriptor
  publication;
- root import does not import `control_plane_kit_core`, FastAPI, HTTP clients,
  Docker clients, cpk-server, or Hello.

Handoff:

- #652 can now install and test a real package in Docker.
- #653 owns the descriptor catalogue shape and completed declaration loading.
- #813 and later own cpk-server process implementation.

Packaging finding:

- A first full `pip install .` attempt with a `git+https` pin failed in
  `python:3.12-slim` because `git` was not installed.
- The dependency was changed to an immutable GitHub archive URL for the same
  commit. This preserves the pin while keeping clean Docker installs light.

## #652 Docker-First Test And Image Harness

#652 adds the first canonical validation harness for
`control-plane-kit-servers`.

Red proof:

```text
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  python -m unittest tests.test_docker_harness
```

Before implementation, the focused tests failed because `test.sh`,
`Dockerfile.test`, harness scripts, and `.github/workflows/tests.yml` did not
exist.

Harness decisions:

- `./test.sh` is Docker-first and does not require host Python;
- `Dockerfile.test` installs the package and archive-pinned core dependency;
- `scripts/run_all_tests.py` runs unittest discovery and the product image lane;
- `scripts/product_image_lane.py` reports `no-products` while the inventory is
  empty;
- `scripts/docker_residue_audit.sh` inspects only resources with the exact
  `org.openj92.project=control-plane-kit-servers` label;
- GitHub Actions runs `./test.sh` on `main`, `develop`, and PRs targeting those
  branches.

Handoff:

- #653 can now rely on `./test.sh` for package and catalogue validation.
- Product image builds remain pending until actual product directories exist.
- cpk-server and Hello image lanes must share harness conventions without
  sharing product ownership.
