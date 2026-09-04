# Hello Server

The next Hello image serves a self-contained HTML greeting at `/`.
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
The catalogue currently pins that older image. Issue #130 pairs the new published
digest with its `HELLO_COLOR` descriptor binding and HTML response verification;
changing source alone does not change a deployed node.
