Source: [products/cpk_server/tests/test_retained_ingress_composition.py](../../../../../products/cpk_server/tests/test_retained_ingress_composition.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This is a process-adapter forwarding witness despite the historical “retained”
filename. A replacement Cloudflare module records create and teardown calls.
The wrapper translates authority/resource coordinates into the interpreter's
types and preserves the supplied resolution and custody grant identities.
A disabled interpreter selection constructs no provider.

The fake deliberately accepts plain objects and SimpleNamespace values. It
does not establish actual grant admission, provider ownership, Cloudflare
mutation, retained reservation behavior or successful deletion. The surface
check excludes three retired methods and verifies the wrapper's redacted repr;
it is not a complete secret-flow audit. Module injection/unloading keeps this
test's product imports isolated.

Related source: [server adapter](../src/control_plane_kit_servers_cpk_server/server.py.md).
