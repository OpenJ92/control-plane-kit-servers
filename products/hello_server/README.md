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
this changed contract is revision 2, distinct from the old plaintext revision 1.
the demo client uses the same product-owned HTML bytes for response verification.
Changing the catalogue alone does not change a deployed node. Preserve the old
descriptor and authored graph when adding alongside an existing plaintext node.

Published source: `cae307b34884e234ee8d96517012fe39c45e3dea`.
Image: `ghcr.io/openj92/control-plane-kit-servers/hello-server@sha256:e3256ca3aeb52077527143c88d96b3b460080862459686e259d2464f41c1669b`.
Platform: **linux/amd64 only**, not a multi-platform image. The target runtime
must support that platform (natively or through explicitly admitted emulation).

## Wrapped source contract (#184)

Current source adds authenticated SDK static and liveness/readiness reads on the
same `internal` HTTP8000 listener. The published revision2 descriptor and digest
above remain unchanged and contain no claim of this wrapper. #191 owns new image
qualification and catalogue adoption. The ordinary package gate exercises this
source on Python3.12; it does not build or qualify the new Hello image separately.

Startup now requires `/etc/cpk/hello/control.json`, read once from an opened regular
file with final-component symlinks rejected and a 65536-byte ceiling. The file
contains public, integrity-sensitive material: exact local target/runtime,
Hello's fixed health-only V2 declaration, distinct static/health issuers and
nominal public-key snapshots. It contains no private signing keys or dependency
URLs. Missing, unconfigured or invalid material prevents socket creation with a
fixed redacted error. No fallback identity, keys or unwrapped mode is generated.
The configured production process requires port 8000; a different HELLO_PORT is
rejected before opening a socket. Changes to configuration require restart.

The product-owned configuration module provides
`decode_hello_control_configuration`, `hello_control_configuration_artifact` and
`hello_source_runtime_contract`. A source composition uses already admitted local
values, never runnable dummy keys or an invented future graph identity:

```python
artifact = hello_control_configuration_artifact(admitted_configuration)
source_contract = hello_source_runtime_contract(artifact)
```

This creates the required `hello-control` JSON slot at the fixed path with 0444
mode and Core-computed digests. A later producer must supply the actual authority
and selected per-instance artifact. Core #1821 / Interpreters #149 own that
delivery and issuer work; Operations currently does not transfer selected node
configuration artifacts into runtime product material. Receiver tests do not
prove mounted configuration, gateway routing or public deployment acceptance.

Each server captures its greeting and selected dependency inputs once, shared
by both legacy handlers and SDK callbacks. Dependency declarations accept at most
8 entries/8192 UTF-8 bytes, names at most 64 characters, environment names at
most128 characters and selected URLs at most 2048 UTF-8 bytes. Overflow is rejected
before socket creation. Environment changes after startup do not reconfigure it.

Readiness retains HTTP status with a capped 16385-byte sample and PostgreSQL TCP
connect meaning; sample overflow alone is not failure, and TCP success does not
prove SQL authentication. An observation starts at most 16 sequential operations,
checks a 5-second monotonic cooperative budget and supplies each operation at most
2 seconds or remaining budget. A late return produces UNKNOWN, never late
HEALTHY; legacy readiness maps this to503 with fixed budget-exhausted text.
Blocking DNS/address attempts or body reads can overrun the budget. It is not a
hard return/cancellation deadline. There is no retry worker, cache or bounded
global thread-count claim.

Normal in-bound HTML, palette, legacy health/dependencies/404 and bounded query-
redacted observation behavior remain; observations are instance-local. Existing
application health routes remain unauthenticated. SDK credential denial runs no
protected dependency or application observation callback. Liveness means the
Hello process can execute its callback; static status is not readiness.
