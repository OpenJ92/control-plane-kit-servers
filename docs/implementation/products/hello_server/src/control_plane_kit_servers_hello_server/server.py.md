Source: [server.py](../../../../../../products/hello_server/src/control_plane_kit_servers_hello_server/server.py).

The product factory validates common configuration and settings, then constructs
the actual accepted SDK CpkThreadingHTTPServer with bind_and_activate=False.
That wrapper prepares and installs authenticated routes before bind/activation;
SDK setup failure closes its unbound socket. The product binds and activates only
after composition and closes on subsequent failure. Main retains its existing
port policy, serving loop and final close. No private lifecycle flag or duplicate
route installer remains in the product.

Hello captures immutable dependency/settings and per-server bounded observations;
dependency inspection supplies the admitted SDK readiness callback. #241 removes
the duplicate public /health/live and /health/ready handlers. Greeting,
dependencies and bounded application observations remain unchanged.
SDK owns purpose-separated verification, full installed target/declaration and
request authority-context congruence. Its actual host lifecycle gates readiness;
fixtures wait for public cpk_is_serving, then shut down, close and join the real
server. Denied requests reach no protected callback or ordinary forwarding.

The source Docker recipe supplies CPK_WRAPPER_CONFIGURATION_FILE for the existing
mounted public configuration. No default key is supplied. HTML, ordinary routes,
network budgets and bounded/redacted observations remain
product-owned. No new persistence, external port, provider mutation, supervisor,
command handler or replay store is added. Static source/target review does not
qualify the historical image; the unchanged whole owner gate remains required.
