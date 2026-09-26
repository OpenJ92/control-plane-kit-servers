Source: [test_image_bootstrap.py](../../../../../products/cpk_server/tests/test_image_bootstrap.py).
Maintain with the bootstrap/product installation and source-host contracts.

Issue231 translates the existing raw-ASGI-query forwarding assertion to the
host's awaited handle_async entrance. It still requires exactly one boundary
call and the exact request.scope["query_string"] bytes; the call must now be
awaited. This preserves query decoding ownership at the process boundary.
The separate real-ASGI awaited-execution tests exercise runtime completion,
identity, errors and cancellation; this source assertion alone proves none of
those behaviors. Other bootstrap/package/runtime assertions remain unchanged.

Issue235 adds the optional managed-health support path to the existing exact
environment declaration assertion and requires its optional status. Existing
secret-free metadata assertions remain intact.
