Source: [test_image_bootstrap.py](../../../../../products/cpk_server/tests/test_image_bootstrap.py).
Maintain with the bootstrap/product installation and source-host contracts.

Servers #316 translates the raw-ASGI-query forwarding call selector from
handle_async to the hosted handle_stream_async entrance. Run 40021647574 passed
all twelve new transport methods but failed this old-name selector (zero calls
found) in the 612-method CPK group. The correction preserves exactly one call,
awaited completion and the exact request.scope["query_string"] expression; it
does not weaken or skip a query assertion. New direct-ASGI tests independently
exercise stream behavior. This failed run does not credit later gate stages.

Servers #297 extends the exact environment-name expectation with
CPK_MANAGED_HEALTH and CPK_MANAGED_HEALTH_CONFIGURATION_FILE, matching the
explicit optional process contract. All preexisting names, ordering, exact-list
comparison and secret-refusal assertions remain. The original required control
file stays first; the optional managed-health file is appended. This update was
identified by source review before running the implementation gate.

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

#345 adds the two explicit workspace-authority environment names to the existing
contract assertion. The private file declaration remains separate from public
configuration artifacts. Existing secret-free checks are unchanged.
