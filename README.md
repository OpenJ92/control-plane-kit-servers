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

assert load_catalogue() == ()
```

The empty catalogue is deliberate until descriptor publication work begins in
#653.
