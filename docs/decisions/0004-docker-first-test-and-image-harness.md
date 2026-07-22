# 0004 Docker-First Test And Image Harness

Status: Accepted

Issue: #652

Decision:

Introduce a repository-local Docker-first harness before product implementation
begins. `./test.sh` builds `Dockerfile.test`, runs unittest discovery inside the
container, executes the product image lane, and then runs a host-side residue
audit limited to the exact `control-plane-kit-servers` ownership label.

The product image lane is present but reports `no-products` while the inventory
is empty. Product-local image builds begin only when product implementation
issues add completed product directories.

Consequences:

- Host Python is not required for validation.
- The package is installed in the test image with the archive-pinned core
  dependency.
- No broad Docker cleanup command is introduced.
- CI runs the same `./test.sh` on `main`, `develop`, and PRs to those branches.

No product implementation enters #652.
