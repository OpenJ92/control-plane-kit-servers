Source: [router_control_fixtures.py](../../../../../products/http_active_router/tests/router_control_fixtures.py).
Maintain with product-local synthetic authority and installed-host tests.

Each fixture generates independent static/health Ed25519 private keys in memory,
constructs nominal Core grants and signs them for an injected fixed verifier
clock. No default authority or private key is saved in product source/configuration.
The fixture instantiates the actual router factory on loopback port0 and owns
external-thread shutdown, worker closure and bounded join. HTTP clients close
and cap response reads. This is a product test helper run by the established
owning suite, not a replacement gate or shared runtime framework.
