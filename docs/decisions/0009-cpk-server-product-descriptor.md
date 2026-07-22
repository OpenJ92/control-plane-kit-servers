# 0009 cpk-server Product Descriptor

Status: Accepted

Issue: #816

Decision:

Publish `cpk-server` as ordinary external product data using the extracted core
`control-plane-kit.product` descriptor language. The descriptor is not built
into core and catalogue loading does not import cpk-server process code.

The descriptor identity is:

```text
ProductIdentity("control-plane-kit", "cpk-server", 1)
```

The product declares:

- an OCI image pinned by digest: `ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:dacf70bb1dac886d24a7abdf101cf9a95bfd5ed54cef036a59fce810c7b76d9e`;
- HTTP API and MCP Streamable HTTP provider sockets;
- Postgres requirement sockets for workplace, activity-history, observer-state,
  and graph-topology stores;
- secret-free bootstrap environment contracts;
- HTTP liveness and readiness verification checks;
- owned ephemeral compute lifecycle.

Consequence:

The Dockerfile copies only product-local source required to run the process, not
`product.cpk.json`, root package catalogue data, or catalogue evidence. This
avoids making the descriptor part of the image it is trying to pin. The
descriptor records the stabilized image source commit and pushed GHCR image
digest as provenance. As of #848, the hosted process uses FastAPI over the
extracted operations application boundary and boots against a caller-supplied
Postgres instance database.

Catalogue admission is explicit:

```text
catalogue/products.json
  -> load_catalogue
  -> descriptor sha256 check
  -> ProductDescriptorCodec.decode_document
  -> image digest agreement
  -> ProductCatalog
```

No recursive proxying enters the descriptor. A parent cpk-server may spawn a
child cpk-server and then navigate directly to the child public endpoint.


Publication lane:

```text
scripts/publish_product_image.sh cpk-server extract-ops-848
  -> ghcr.io/openj92/control-plane-kit-servers/cpk-server:extract-ops-848
  -> ghcr.io/openj92/control-plane-kit-servers/cpk-server@sha256:dacf70bb1dac886d24a7abdf101cf9a95bfd5ed54cef036a59fce810c7b76d9e
```

A GitHub Actions `workflow_dispatch` entrypoint can publish future server
products using `GITHUB_TOKEN` with `packages: write`.


Current GHCR visibility:

```text
https://github.com/users/OpenJ92/packages/container/package/control-plane-kit-servers%2Fcpk-server
visibility: private
```

Authenticated Docker Desktop and GitHub Actions can pull the digest. Public
unauthenticated pulls require an explicit package visibility decision.
