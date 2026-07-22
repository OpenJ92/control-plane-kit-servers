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


## #653 Descriptor Catalogue And Publication Artifacts

#653 defines the server-product publication catalogue without implementing a
server product. The catalogue is metadata about completed products, not a second
core descriptor language and not an application bootstrap.

Red proof:

```text
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -c 'python -m unittest tests.test_descriptor_catalogue -v'
```

Before implementation, the focused tests failed because the catalogue language,
strict declaration value, and publication helper did not exist.

Objects introduced:

```python
PublishedProductDescriptor
  = product_id
  x owner_directory
  x descriptor_path
  x descriptor_sha256
  x source_commit
  x image_ref
  x image_digest
  x status
```

Publication morphism:

```text
catalogue/products.json
  -> load_catalogue
  -> tuple[PublishedProductDescriptor, ...]
  -> publish_catalogue
  -> deterministic JSON + sha256 sidecar
```

Laws proven:

- default installed catalogue is empty and immutable;
- only completed declarations load;
- duplicates fail closed;
- unknown fields fail closed;
- descriptor/source/image digests are explicit;
- publication ordering and checksum are deterministic;
- catalogue loading does not import product implementation or process code.

Handoff:

- #813 can add cpk-server declaration material as ordinary product data once the
  wrapper exists.
- #816 must prove cpk-server image and descriptor digests before adding a
  completed catalogue declaration.
- Hello issues must follow the same catalogue path; no special built-in route is
  available.


## #813 cpk-server Process Composition

#813 creates the first product-local cpk-server wrapper without implementing
HTTP/MCP process routes or an OCI image. The package lives under
`products/cpk_server/src/control_plane_kit_servers_cpk_server`, keeping the root
server catalogue import light and keeping the product independently movable.

Red proof:

```text
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -c 'python -m pip install . >/tmp/pip.log && \
         python -m unittest discover -s products/cpk_server/tests -v'
```

Before implementation, the installed package had core available but no
`control_plane_kit_servers_cpk_server` module and no product-local #813 law
cards.

Objects introduced:

```python
CpkServerProcessConfiguration
  = execution_enabled x control_token_configured x mode

CpkServerProcessState
  = targets x active_target x observers x graph_truth_policy

CpkServerComposition
  = configuration x CpkServerEntrypointHandoffContract x process_state
```

Composition morphism:

```text
CpkServerProcessConfiguration
  -> create_cpk_server_composition
    -> CpkServerComposition
      -> CpkServerEntrypointHandoffContract
        -> DeploymentProgramBoundary + HTTP contract + MCP contract + UoW boundary
```

Laws proven:

- product-local law cards assign the #813-owned #804 laws;
- execution-capable composition requires auth configuration;
- HTTP and MCP share the same core handoff/program boundary;
- observer mutation changes immutable process state, not graph truth;
- replacing target sets clears stale active target state;
- unknown target switches fail closed;
- root catalogue import does not import cpk-server;
- core import does not import cpk-server;
- Hello cannot satisfy cpk-server laws.

Handoff:

- #814 implements HTTP/MCP process boundaries over this composition and must not
  create another command vocabulary.
- #815 packages the process as OCI after #814.
- #816 adds product descriptor and catalogue publication only after image and
  descriptor digest evidence exists.


## #814 cpk-server HTTP And MCP Boundaries

#814 adds framework-neutral HTTP and MCP process boundaries over the #813
composition root. The purpose is to prove route/protocol shape and shared
delegation before introducing FastAPI, hosted MCP process bootstrap, or an OCI
image.

Red proof:

```text
docker run --rm -v "$PWD":/app -w /app python:3.12-slim \
  sh -c 'python -m pip install . >/tmp/pip.log && \
         python -m unittest discover -s products/cpk_server/tests -v'
```

Before implementation, the #814 tests failed because
`CpkServerHttpProcessBoundary`, `CpkServerMcpProcessBoundary`, and the shared
application boundary did not exist.

Objects introduced:

```python
CpkServerApplicationBoundary
  = ControlPlaneServiceRole -> service.handle(request)

CpkServerHttpProcessBoundary
  = CpkServerComposition x CpkServerApplicationBoundary

CpkServerMcpProcessBoundary
  = CpkServerComposition x CpkServerApplicationBoundary

CpkServerServiceRequest
  = surface x route_id x service_role x path_parameters x payload
```

Morphism:

```text
HTTP route / MCP message
  -> core route id
    -> service role
      -> CpkServerApplicationBoundary
        -> one service object
```

Laws proven:

- HTTP read route delegates to the shared reads service;
- HTTP command route requires bearer authorization and delegates to planning;
- malformed and oversized request bodies fail before service dispatch;
- MCP `tools/call` and HTTP use the same application boundary;
- MCP `resources/read` uses the same reads service;
- missing MCP auth fails closed;
- unknown HTTP/MCP operations fail closed and do not touch services.

Deliberate hardening:

- The frozen block-control development fixture allowed unconfigured local
  mutation calls. Hosted cpk-server does not preserve a mutation-capable
  unauthenticated mode. This matches the refreshed #814 law that control-route
  mutation requires configured authentication.

Handoff:

- #815 can wrap these framework-neutral boundaries in a runnable process/image.
- #816 must keep descriptor/catalogue publication declaration-only and avoid
  importing these process modules during catalogue loading.
- #817 can use the same boundaries for live smoke evidence.
