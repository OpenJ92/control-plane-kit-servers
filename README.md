# control-plane-kit-servers

Reusable OCI server products and descriptors for `control-plane-kit`.

This repository starts as an empty server-product catalogue foundation. It does
not yet contain `cpk-server`, Hello, CoreDNS, routers, gateways, or any other
product implementation.

The repository has two bootstrap responsibilities, executed in order by the
EXTRACT.F issue topology:

```text
products/cpk_server
  the control-plane process wrapper that imports the pinned core package and
  exposes HTTP, MCP, health, configuration, image, and descriptor artifacts

products/hello
  the first ordinary reusable server product transferred with isomorphic tests
  and live Docker proof
```

`control-plane-kit-core` never imports this repository. Server products may
import the pinned core release candidate to express descriptors, socket
contracts, and process handoff contracts.

See:

- `coordination/core-release-candidate.json`
- `coordination/product-inventory.json`
- `coordination/extract-f-804-cpk-server-handoff.json`
- `docs/issue-transfer-strategy.md`
- `docs/decisions/0001-repository-foundation.md`
- `docs/security/0001-foundation-review.md`

Current package surface:

```python
from control_plane_kit_servers import load_catalogue

assert [item.product_id for item in load_catalogue()] == ["cpk-server"]
```

The catalogue currently has the completed-product publication language and
publishes `cpk-server` as the first completed product declaration. `hello`
remains reserved for later transfer.

Publication source and generated artifacts are intentionally separate:

```text
catalogue/products.json
  -> scripts/publish_catalogue.py
    -> dist/server-products.json
    -> dist/server-products.json.sha256
```

`load_catalogue()` reads completed publication records only. It never imports
product process code, FastAPI apps, Docker clients, stores, or entrypoints.


## cpk-server Image Foundation

`products/cpk_server` now contains a runnable image definition for the
control-plane process wrapper. This is now paired with a published descriptor in
`products/cpk_server/product.cpk.json` and a catalogue declaration containing
descriptor, image, and source digest evidence.

Local smoke:

```bash
sh scripts/cpk_server_image_smoke.sh
```


## Publishing Product Images

The first product image is published at:

```text
ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:dacf70bb1dac886d24a7abdf101cf9a95bfd5ed54cef036a59fce810c7b76d9e
```

Per-product publication uses:

```bash
sh scripts/publish_product_image.sh cpk-server extract-ops-848
```

Each product must be admitted explicitly by the script. There is no broad
publish-all path.


Current GHCR visibility:

```text
https://github.com/users/OpenJ92/packages/container/package/control-plane-kit-servers%2Fcpk-server
visibility: private
```

Authenticated Docker Desktop and GitHub Actions can pull the digest. Public
unauthenticated pulls require an explicit package visibility decision.
