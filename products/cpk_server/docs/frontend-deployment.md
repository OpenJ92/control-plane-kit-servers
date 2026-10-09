# Retained website composition

Servers #243 interprets the web-owned serving contract merged at
[`221ad6d`](https://github.com/OpenJ92/control-plane-kit-web/blob/221ad6dbb409f7765517b7b4efbfdab040b65544/docs/serving.md).
The website serves built React assets and forwards a closed set of authenticated
API requests to one configured CPK HTTPS origin. Its implementation and image
remain owned by the web repository. The packaging interface JSON is documentation,
not a CPK descriptor to submit directly.

`client.frontend.frontend_product` returns an ordinary `ContainerServerProduct`.
`compose_frontend_deployment` returns an ordinary `DeploymentTopology` containing
that website and a selected revision-1 cloudflared connector. These functions
perform no IO, build, credential resolution, admission or execution. They do not
modify root bootstrap, register a product, create a workspace or select a current
graph. The existing public client remains the execution path.

## Inputs and example

Supply a separately reviewed `OciImageReference`, preserving its actual registry,
repository, digest, platform and provenance. This source change supplies **no
image digest** and makes no claim that an image exists or has been published.
Load the connector through `ProductDescriptorCodec` from the selected compatible
release. The function refuses a document whose bytes and product disagree, or a
connector contract outside the existing ordinary profile.

```python
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.public_ingress import (
    IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget,
)
from control_plane_kit_core.runtime_authority import RuntimeAuthorityReference
from control_plane_kit_core.topology import compile_topology, validate_graph
from control_plane_kit_servers_cpk_server.client.frontend import (
    compose_frontend_deployment, frontend_product,
)

def describe_frontend(reviewed_image, selected_connector):
    upstream = "https://cpk.example.test"
    product = frontend_product(reviewed_image, upstream=upstream)
    topology = compose_frontend_deployment(
        image=reviewed_image, upstream=upstream,
        workspace_id="frontend-workspace", runtime_id="frontend-runtime",
        network_name="cpk-frontend-network",
        authority_ref=RuntimeAuthorityReference("approved-local-docker"),
        connector_product=selected_connector,
        ingress=NamedPublicIngress(
            "frontend-public", IngressAuthorityReference("approved-zone"),
            PublicIngressTarget("website", "http"),
            "frontend-connector", "web.example.test",
        ),
    )
    graph = compile_topology(topology)
    if not validate_graph(graph).valid:
        raise ValueError("frontend graph is invalid")
    return ProductDescriptorCodec().encode_document(product), graph
```

All names and hostnames above are examples, not provider instructions. Author and
review the actual coordinates before submission. The returned product descriptor
and graph use existing canonical codecs; register/select through existing public
CPK routes. Product identity incorporates canonical image and runtime contract
material, so changes cannot silently keep the same material identity.

`CPK_WEB_UPSTREAM` is required public configuration. The authoring helper accepts
bounded canonical HTTPS origins: ordinary lowercase ASCII DNS labels (already
punycode for IDNs), canonical IPv4 and compressed IPv6, and optional nondefault
ports. It rejects credentials, paths, queries, fragments, URL normalization
aliases and explicit default port 443. Errors omit rejected values. The web
process remains the final validator; this helper deliberately supports a bounded
subset of its URL parser, not a second general URL implementation.

The provider socket is `http`. Container port defaults to 8080; `port=` must be an
integer from 1024 to 65535 and changes both `PORT` and the provider port. The image
owns its non-root user, entrypoint and read-only-compatible process. This composer
does not override them. The web instance has no secret delivery, Docker socket,
provider credential, injected CPK identity, protected control surface or data
volume. The runtime authority reference selects where CPK executes; it does not
deliver that authority to the website.

## Retention and evidence

The frontend uses a **separate public API workspace** from managed Hello on the
same approved Docker host. A Core graph has a `name`, not an authoritative
workspace ID: `workspace_id` names the topology here, and the caller must use that
workspace in the public client request. Matching graph names cannot authorize or
prove isolation. Before #225 effects, check the actual workspace, network,
resource and ingress inventory, including the unchanged grandparent origin.

The named ingress targets the website directly and is distinct from Hello's
management ingress. The composer does not add a gateway or SDK receiver. Retain
the frontend workspace while submitting Hello's explicitly empty desired graph;
never submit that teardown to the frontend workspace. Keeping the separate
workspace is the lifetime boundary, not permanent resource retention. The
supplied ingress lifecycle is preserved, and eventual frontend removal still
requires its own exact inspected and approved plan.

The website's verification contract is empty. **Readiness is unverified.**
`no-verification-contract` is an ordinary deployment result, not a successful
health check. No healthy/ready badge may be inferred from it or container start.
There are no native probes or protected health capabilities. Managed-Hello's
health requirements remain unchanged. Source tests protect pure values only;
joint web #6 / Servers #225 browser evidence must separately record time-bound
asset serving, authenticated API and approval usability, and website availability
after Hello teardown. Approval remains distinct from execution.

No new durable transaction/history owner is introduced. Public save, prepare,
approval and execution retain existing records and uncertainty rules. Final
compatible dependency/image selection belongs to Servers #181/#225; this helper
does not qualify the historical selected product images for the future live run.
