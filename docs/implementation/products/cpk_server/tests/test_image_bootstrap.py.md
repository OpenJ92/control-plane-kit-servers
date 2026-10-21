Source: [test_image_bootstrap.py](../../../../../products/cpk_server/tests/test_image_bootstrap.py).
Maintain with the bootstrap/product installation and source-host contracts.

Servers #294 extracts the existing pure SecretProviderBootstrapRegistry
construction into _provider_bootstrap_registry so it can validate before schema
mutation. Kepler SOURCE review identified the exact-name bootstrap import
allowlist needed that new helper. Only this owner is added; the same AST walk
and zero-violations assertion remain. The helper constructs immutable registry
values, never credentials or a provider client. This correction was made before
source execution; it does not change the16 reviewed managed-health targets.

Issue231 translates the existing raw-ASGI-query forwarding assertion to the
host's awaited handle_async entrance. It still requires exactly one boundary
call and the exact request.scope["query_string"] bytes; the call must now be
awaited. This preserves query decoding ownership at the process boundary.
The separate real-ASGI awaited-execution tests exercise runtime completion,
identity, errors and cancellation; this source assertion alone proves none of
those behaviors. Other bootstrap/package/runtime assertions remain unchanged.
