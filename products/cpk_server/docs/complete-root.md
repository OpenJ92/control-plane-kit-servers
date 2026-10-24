# Complete local root with a website

The optional `installation.website` field connects the accepted installation
composer to the existing root bootstrap planner, acquisition receipt and public
setup. Keep input schema `cpk.root-bootstrap.input.v1` and the three selected
backend documents. Supply current CPK and Secrets source contracts containing
the public control artifacts from [offline commissioning](root-commissioning.md).
Their images still require separate source/platform qualification.

With an already reviewed Core OCI image value, add the website input:

```python
document["installation"]["website"] = {
    "image": reviewed_website_image.descriptor(),
    "external_endpoint": "https://web.example.test",
    "host_binding": {"address": "127.0.0.1", "port": 18081},
}
plan = plan_root_bootstrap(document, driver_image_id=reviewed_driver_image_id)
```

The website binding must differ from the API's top-level loopback binding. The
image is the complete Core descriptor, not a string or unqualified tag. Both
external endpoints must satisfy the shared canonical-origin rules and use
distinct hosts. Bootstrap allocates no public ingress or connector resources.
The website's upstream is derived from the API endpoint; it is not independently
supplied. Website readiness and external HTTPS/browser usability remain
unverified by this local acquisition.

The enabled profile requires exactly one `cpk-control` artifact at
`/etc/cpk/cpk-server/control.json` and one `secrets-control` artifact at
`/etc/cpk/secrets-server/control.json`. Both are public JSON, mode0444, at most
65536 UTF-8 bytes, and selected through their actual environment and control
surface declarations. The actual product decoders enforce each product's
receiving policy. Workspace/runtime/node/socket must match the installation,
and supplied receiver IDs must be valid and distinct. Original content and
source digests survive admission. No private key or commissioning directory
belongs in bootstrap input or material.

Review the plan's four-node graph, `website_node_id`, two `host_bindings` and
four `setup_products`. The first three setup documents retain their original
canonical input order; the fourth is the actual derived website product.
Website adds no credential, secret-file input or runtime socket. Changes to
image, origins, bindings or public artifacts change the plan digest; saved-plan
drift is refused before material resolution.

During acquisition, each container's complete observed port tuple must match
the plan after start: API and website each have one TCP8080 mapping on the
approved loopback port; PostgreSQL and Secrets have none. Missing, duplicate,
extra or incorrect mappings hold with start still pending. Exact fixed-field
observations enter the receipt before pending is cleared. Public setup imports
all four exact products and verifies their returned identities using the
existing progress files and routes.

An interrupted or mismatched observation is not permission to retry apply.
Existing receipts preserve uncertainty and prevent redispatch; inspect the
owned state and follow the explicit operator process. This change adds no
rollback, receipt migration or provider adoption. Retained external tunnel/DNS
inventory stays outside receipt-owned cleanup. Omitting website preserves the
original three-product plan, lazy imports and acquisition/setup branches.
