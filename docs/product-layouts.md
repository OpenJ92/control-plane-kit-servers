# Product Layouts

## Allowed product layout

```text
products/<product_id>/
  descriptor.py          # graph-visible value declarations only
  image/                 # Dockerfile, image build context, digest evidence
  entrypoint/            # runnable process/bootstrap code
  tests/                 # product-owned unit, architecture, and live tests
  examples/              # focused scenarios and operator-readable demos
  docs/                  # product decision logs and learning notes
```

`descriptor.py` may import pinned core value types and local declaration values.
It must not import `entrypoint/`, start processes, contact Docker, open network
connections, read secrets, or mutate stores.

`entrypoint/` owns process composition. It may import local product language,
local product operations, and pinned core contracts required to expose the
server.

`image/` owns OCI material and digest evidence for exactly one product.

`tests/` owns isomorphic successor tests for the product and any live proof that
the issue requires.

Bootstrap reserved layouts:

```text
products/cpk_server
products/hello
```

These names are reserved by `coordination/product-inventory.json`, but their
implementation directories are not created until their implementation issues
open.

No shared support without evidence from two products or an explicit bootstrap
exception. Catalogue imports declaration entrances only.

## Forbidden product layout

```text
products/
  catalog.py             # imports entrypoint modules or Docker build code
  shared.py              # created before two products need it
  cpk_server/            # empty placeholder before #813 begins
  hello/                 # empty placeholder before Hello transfer begins
```

Forbidden patterns:

- catalogue loading imports process code;
- descriptor loading starts Docker or reads process environment;
- one product reaches into another product directory;
- package root imports FastAPI apps or product implementation modules;
- product descriptors contain secrets;
- cleanup uses broad Docker prune;
- cpk-server laws are satisfied by Hello or any ordinary product;
- Hello laws are satisfied by cpk-server process behavior.
