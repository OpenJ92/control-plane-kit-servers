# Hello Server

The pinned Hello image serves a self-contained HTML greeting at `/`.
Set `HELLO_MESSAGE="Hello Jacob"` and `HELLO_COLOR=blue` for the blue page.
The greeting is displayed directly and HTML-escaped, never interpreted as markup.

`HELLO_COLOR` accepts exactly `blue` (the default), `purple`, `green`, or `red`.
An unsupported explicit value prevents startup with a fixed configuration error.
These are process environment inputs, not graph display metadata.
Health, dependency and bounded request-observation endpoints are unchanged.

`render_hello(message, color)` in the product's `server` module owns the exact
UTF-8 response bytes for matching-image verification. It has no network or file
effects. There is no plaintext/HTML mode switch, JavaScript, or external asset.

Previously published image digests still serve their original plaintext response.
The catalogue pairs the HTML image with its `HELLO_COLOR` descriptor binding;
the demo client uses the same product-owned HTML bytes for response verification.
Changing the catalogue alone does not change a deployed node. Preserve the old
descriptor and authored graph when adding alongside an existing plaintext node.

Published source: `cae307b34884e234ee8d96517012fe39c45e3dea`.
Image: `ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:e3256ca3aeb52077527143c88d96b3b460080862459686e259d2464f41c1669b`.
Platform: **linux/amd64 only**, not a multi-platform image. The target runtime
must support that platform (natively or through explicitly admitted emulation).
