# 0003 Package Metadata And Catalogue Entrance

Status: Accepted

Issue: #651

Decision:

Create the `control-plane-kit-servers` Python distribution with a pinned
bootstrap dependency on `control-plane-kit-core` at the accepted EXTRACT.E/F
coordination commit. The pin uses the immutable GitHub archive URL rather than
`git+https`, so clean Docker installs do not require a git executable. The
package root exposes only `__version__` and `load_catalogue()`.

The catalogue entrance is intentionally empty and immutable until #653 defines
the descriptor catalogue publication shape. It does not import cpk-server,
Hello, FastAPI apps, Docker build code, product implementation modules, or
stores.

Consequences:

- #652 can build the Docker-first package/test harness around a real package.
- #653 can replace the empty catalogue assembly with completed declaration
  loading without changing the root import contract.
- #813-#817 can add `products/cpk_server` without making root import execute a
  process.

No product implementation enters #651.
