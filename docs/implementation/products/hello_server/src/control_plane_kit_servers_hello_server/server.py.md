Source: [server.py](../../../../../../products/hello_server/src/control_plane_kit_servers_hello_server/server.py).
Maintain with listener composition and application behavior.

Production validates port8000, palette, fixed configuration and dependency inputs
before creating a socket. create_hello_server captures one frozen settings value,
creates exact standard ThreadingHTTPServer with bind_and_activate=False, installs
SDK routes, then binds/activates. Installation/bind failures close the socket;
main closes it when serving exits. Tests inject ephemeral addresses but separately
assert the production port policy. No SDK process supervisor or same-thread
shutdown call is introduced; the existing threaded-host model is retained.

The same per-server dependency snapshot feeds the ordinary legacy readiness
handler and SDK's admitted callback. No handler rereads os.environ. Static/health
verifiers use separate holders, issuers and purposes, with integer Unix time;
the health dispatcher binds exact local target/runtime/declaration. SDK owns
authentication/protocol, Hello owns health meaning. No command verifier, variables
or replay store is configured. Denial reaches no product callbacks.

Escaped HTML and ordinary route responses remain. Budget exhaustion is a new
explicit legacy503/SDK UNKNOWN result; legacy application health stays public.
Request observations are bounded and instance-local, stripping query strings.
Dependency/config values are absent from results/logging. No persistence,
provider operations, automatic recovery or new listener/public port is added.
